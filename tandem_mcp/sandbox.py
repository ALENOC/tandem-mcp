"""What the executor may touch: paths inside a workspace, commands that match an allow list.

Two layers guard the commands the executor chooses. The first is a check of the command text:
every part of a pipeline or a chain must match the allow list, none may match the safety list,
command substitution is refused and a redirection must point at a writable file. The second,
where bubblewrap is installed, is an operating system sandbox: the whole machine is read only,
only the workspace is writable, credentials folders are hidden and there is no network."""
import collections
import hashlib
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
from pathlib import Path

# Never run for the executor, whatever the allow list says.
# Refused wherever they stand in a command part.
DENY = [r'\bsudo\b', r'\bdoas\b', r'\brm\s+(-\w*\s+)*-\w*r\w*\s+(/|~|\$HOME)(\s|$)',
        r'\bgit\s+(push|commit|reset|clean|checkout|rebase|merge|tag|restore|stash|config|remote)\b',
        r'\bmkfs', r'\bdd\s+if=', r'\bcurl\b.*\|\s*(ba)?sh', r'\bwget\b.*\|\s*(ba)?sh',
        r'\bchmod\s+-R\b', r'>\s*/dev/sd', r'\bnpm\s+publish\b', r'\bpip3?\s+install\b']
# Refused as the command of a part. As an argument they are plain words: `grep source x`, `cat docs/ssh.md`.
DENY_COMMANDS = {'su', 'shutdown', 'reboot', 'chown', 'systemctl', 'kill', 'killall', 'pkill', 'ssh', 'scp', 'rsync', 'nc',
                 'apt', 'apt-get', 'crontab', 'eval', 'exec', 'source', '.'}
# Commands that run another command given as an argument: there the names above are looked up in the whole part.
WRAPPERS = {'env', 'command', 'builtin', 'time', 'nice', 'ionice', 'nohup', 'timeout', 'xargs', 'stdbuf', 'setsid', 'watch',
            'sh', 'bash', 'dash', 'zsh', 'ksh', 'find', 'parallel', 'strace', 'flock'}
_DENY_NAMES = re.compile(r'(?<![\w./-])(?:' + '|'.join(re.escape(n) for n in sorted(DENY_COMMANDS - {'.'})) + r')(?![\w.-])')
_ASSIGNMENT = re.compile(r'^[A-Za-z_]\w*=')
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'managed_components', '.history', 'dist', '.cache'}
SECRETS = ['.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.config/gh', '.config/gcloud', '.password-store',
           '.netrc', '.git-credentials', '.npmrc', '.pypirc', '.claude', '.codex', '.gemini',
           '.local/share/keyrings', '.gradle/gradle.properties', '.m2/settings.xml', '.m2/settings-security.xml',
           '.cargo/credentials', '.cargo/credentials.toml',
           '.config/google-chrome', '.config/chromium', '.mozilla']

_PEM_BLOCK_RE = re.compile(
    r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----'
)
_TOKEN_RE = re.compile(
    r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
    r'|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[0-9A-Za-z-]{10,}'
    r'|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|ya29\.[A-Za-z0-9_-]{20,})\b'
)
_ENV_ASSIGN_RE = re.compile(
    r'(?im)^([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*([^\s\'"#]+|"[^"\n]+"|\'[^\'\n]+\')'
)
_BEARER_RE = re.compile(r'(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]{16,}')


def _mask_env(m):
    if SECRET_ENV.search(m.group(1)):
        return m.group(1) + '=[REDACTED]'
    return m.group(0)


def redact_secrets(text):
    """Mask private key blocks, known API tokens and secret env assignments before returning text."""
    if not text or os.environ.get('TANDEM_REDACT', '1').strip().lower() in ('0', 'off', 'false', 'no'):
        return text
    out = _PEM_BLOCK_RE.sub('[REDACTED_PRIVATE_KEY]', text)
    out = _TOKEN_RE.sub('[REDACTED_TOKEN]', out)
    out = _BEARER_RE.sub(r'\1[REDACTED_TOKEN]', out)
    out = _ENV_ASSIGN_RE.sub(_mask_env, out)
    return out
TEST_DIR = re.compile(r'^(tests?|specs?|__tests__|e2e|unit_tests|integration_tests)$', re.I)
TEST_FILE = re.compile(r'^(?:test_.*\.py|.*_test\.(?:py|go|rs)|.*\.(?:test|spec)\.[jt]sx?|conftest\.py|pytest\.ini)$', re.I)
TEST_RUNNERS = re.compile(
    r'\b(?:pytest|py\.test|nosetests|tox|nox|vitest|jest|mocha|ava|tap|ctest|rspec|phpunit)\b'
    r'|\bpython[23]?\s+-m\s+(?:pytest|unittest)\b'
    r'|\b(?:npm|pnpm|yarn|bun|cargo|go|dotnet|mvn|gradle)\s+test\b'
)
SECRET_ENV = re.compile(
    r'(?:^|_)(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|CREDENTIALS|AUTH|COOKIE|PRIVATE|DSN|CONNECTION_STRING)(?:_|$)'
    r'|(?:PASSWORD|PASSWD|_PWD)$'
    r'|^(?:DATABASE|DB|REDIS|MONGO\w*|POSTGRES\w*|MYSQL|AMQP|BROKER)_UR[LI]$'
    r'|^(?:AWS_|AZURE_|GCP_|GOOGLE_APPLICATION_|GITHUB_|GITLAB_|OPENAI_|ANTHROPIC_|GEMINI_|HF_|NPM_|PYPI_|DOCKER_)',
    re.I,
)


def _strip_rel_prefix(path):
    """Normalize separators and strip leading './' prefixes without stripping leading dots of dotfiles."""
    s = str(path).replace(os.sep, '/').replace('\\', '/')
    while s.startswith('./'):
        s = s[2:]
    return s


def _glob_to_re(pattern):
    """Translate a POSIX path glob to a regex where * never crosses '/' and ** does."""
    pattern = _strip_rel_prefix(pattern)
    parts, i, n = ['^'], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == '*':
            if i + 1 < n and pattern[i + 1] == '*':
                if i + 2 < n and pattern[i + 2] == '/':
                    parts.append('(?:.+/)?')
                    i += 3
                    continue
                parts.append('.*')
                i += 2
                continue
            parts.append('[^/]*')
        elif c == '?':
            parts.append('[^/]')
        elif c == '[':
            j = i + 1
            if j < n and pattern[j] in '!^':
                j += 1
            if j < n and pattern[j] == ']':
                j += 1
            while j < n and pattern[j] != ']':
                j += 1
            if j < n:
                body = pattern[i + 1:j]
                if body.startswith('!'):
                    body = '^' + body[1:]
                parts.append(f'[{body}]')
                i = j
            else:
                parts.append(r'\[')
        else:
            parts.append(re.escape(c))
        i += 1
    parts.append('$')
    return re.compile(''.join(parts))


def glob_match(rel, pattern, match_basename=False):
    """Match a workspace-relative path against a glob without '*' crossing '/'."""
    rel = _strip_rel_prefix(rel)
    pat = _strip_rel_prefix(pattern)
    if not pat or not rel or rel.startswith('/') or pat.startswith('/'):
        return False
    if '..' in rel.split('/') or '..' in pat.split('/'):
        return False
    rx = _glob_to_re(pat)
    if rx.match(rel):
        return True
    if match_basename and '/' not in pat:
        return bool(rx.match(rel.rsplit('/', 1)[-1]))
    return False


class SandboxError(RuntimeError):
    pass


def denied(part):
    """True when one part of a command is on the safety list."""
    if any(re.search(pattern, part) for pattern in DENY):
        return True
    try:
        words = shlex.split(part)
    except ValueError:
        words = part.split()
    while words and _ASSIGNMENT.match(words[0]):
        words.pop(0)
    if not words:
        return False
    head = os.path.basename(words[0])
    if head in DENY_COMMANDS:
        return True
    return head in WRAPPERS and bool(_DENY_NAMES.search(part))


def _system_folder(root):
    """Why `root` cannot be a workspace, or ''."""
    home = Path.home().resolve()
    if root == Path(root.anchor) or root == home or root in home.parents:
        return 'workspace must be a project folder, not / or the home folder'
    for name in ('/usr', '/usr/local', '/var', '/var/tmp', '/opt', '/srv', '/run', '/root', '/home', '/mnt', '/media', '/tmp'):
        if root == Path(name).resolve():
            return f'workspace must be a project folder, not {name}'
    for name in ('/etc', '/boot', '/dev', '/proc', '/sys', '/bin', '/sbin', '/lib', '/lib64', '/usr/bin', '/usr/sbin', '/usr/lib'):
        system = Path(name).resolve()
        if root == system or system in root.parents:
            return f'workspace cannot be {name} or a folder inside it'
    for name in SECRETS:
        secret = home / name
        if root == secret or secret in root.parents:
            return f'workspace cannot be the credentials folder ~/{name} or a folder inside it'
    return ''


# the text of a command ---------------------------------------------------------------------------
def split_command(command):
    """Parts of a shell command between ; && || | & and line ends, quotes respected.
    Returns (parts, redirection targets). Command substitution is refused."""
    parts, targets, cur, quote, i = [], [], [], '', 0
    n = len(command)
    while i < n:
        c = command[i]
        if quote:
            if c == '\\' and quote == '"' and i + 1 < n:
                cur.append(command[i:i + 2])
                i += 2
                continue
            if quote == '"' and (c == '`' or command.startswith('$(', i)):
                raise SandboxError('command substitution is not allowed')
            if c == quote:
                quote = ''
            cur.append(c)
        elif c in '\'"':
            quote = c
            cur.append(c)
        elif c == '\\' and i + 1 < n:
            cur.append(command[i:i + 2])
            i += 1
        elif c == '`' or command.startswith('$(', i) or command.startswith('<(', i) or command.startswith('>(', i):
            raise SandboxError('command substitution is not allowed')
        elif c == '$' and i + 1 < n and command[i + 1] in '\'"':
            # $'..' and $".." are read differently by dash and bash: the split below could disagree with the shell
            raise SandboxError("$'...' and $\"...\" quoting is not allowed")
        elif c == '#' and (not cur or cur[-1][-1] in ' \t'):
            # a comment: the shell drops it, so it must not count as text that matches the allow list
            while i < n and command[i] != '\n':
                i += 1
            continue
        elif command.startswith('<<', i):
            raise SandboxError('heredoc and herestring are not allowed')
        elif c == '>':
            j = i + 1
            if j < n and command[j] in '>|':
                j += 1
            if j < n and command[j] == '&':                      # 2>&1 and the like, or &> file
                j += 1
            while j < n and command[j] in ' \t':
                j += 1
            k = j
            while k < n and command[k] not in ' \t;|&<>\n':
                k += 1
            targets.append(command[j:k].strip('\'"'))
            cur.append(command[i:k])
            i = k
            continue
        elif c in ';|&\n':
            parts.append(''.join(cur).strip())
            cur = []
            if c in '|&' and i + 1 < n and command[i + 1] == c:
                i += 1
        else:
            cur.append(c)
        i += 1
    if quote:
        raise SandboxError('unbalanced quote in the command')
    parts.append(''.join(cur).strip())
    return [p for p in parts if p], targets


class Workspace:
    def __init__(self, root, write_globs=None, allow_run=None, immutable=None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise SandboxError(f'workspace is not a folder: {root}')
        why = _system_folder(self.root)
        if why:
            raise SandboxError(why)
        self.write_globs = [g for g in (write_globs or []) if g.strip()]
        self.immutable = [g for g in (immutable or []) if g.strip()]
        try:
            self.allow_run = [re.compile(r) for r in (allow_run or []) if r.strip()]
        except re.error as exc:
            raise SandboxError(f'allow_run holds a bad regular expression: {exc}') from exc
        self.protected = set()             # files and folders the acceptance checks rely on
        self.claims = None                 # shared {path: task name} when tasks run side by side
        self.run_lock = None               # shared lock serializing parallel shell commands
        self.name = ''

    def path(self, rel):
        rel = str(rel)
        p = (self.root / rel).resolve() if not os.path.isabs(rel) else Path(rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise SandboxError(f'path outside the workspace: {rel}')
        return p

    def rel(self, p):
        return str(Path(p).resolve().relative_to(self.root))

    def _in_globs(self, r):
        return any(glob_match(r, g, match_basename=False) for g in self.write_globs)

    def _is_immutable(self, r):
        return any(glob_match(r, g, match_basename=False) for g in self.immutable)

    def is_protected(self, r):
        parts = Path(r).parts
        if any(str(Path(*parts[:k])) in self.protected for k in range(1, len(parts) + 1)):
            return True
        return self._is_immutable(r)

    def protect(self, verify_commands):
        """Files named by the acceptance checks (and test folders/files when a test runner is
        detected) become read only for the executor, unless a write glob names them."""
        runner_used = False
        for command in verify_commands:
            if TEST_RUNNERS.search(command):
                runner_used = True
            try:
                words = shlex.split(command)
            except ValueError:
                words = command.split()
            for word in words:
                word = word.split('::')[0]                        # pytest node ids
                if not word or word.startswith('-') or len(word) > 300:
                    continue
                try:
                    p = self.path(word)
                except (SandboxError, OSError, ValueError):
                    continue
                if p == self.root or not p.exists():
                    continue
                r = self.rel(p)
                if p.is_file() or any(TEST_DIR.match(part) for part in Path(r).parts):
                    self.protected.add(r)
        if runner_used:
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()]
                for d in list(dirnames):
                    if TEST_DIR.match(d):
                        self.protected.add(self.rel(Path(dirpath) / d))
                        dirnames.remove(d)
                for name in filenames:
                    if (Path(dirpath) / name).is_symlink():
                        continue
                    if TEST_FILE.match(name):
                        self.protected.add(self.rel(Path(dirpath) / name))
        return sorted(self.protected)

    def writable(self, rel):
        p = self.path(rel)
        if p == self.root:
            raise SandboxError('that is the workspace folder, not a file')
        r = self.rel(p)
        parts = Path(r).parts
        if '.git' in parts:
            raise SandboxError('the .git folder is not writable')
        skip_hit = next((part for part in parts if part in SKIP_DIRS), None)
        if skip_hit and not self._in_globs(r):
            raise SandboxError(f'{r} is inside {skip_hit} and is read only')
        if self._is_immutable(r):
            raise SandboxError(f'{r} is declared immutable and is read only')
        if self.write_globs and not self._in_globs(r):
            raise SandboxError(f'{r} is outside the files this task may write ({", ".join(self.write_globs)})')
        if self.is_protected(r) and not self._in_globs(r):
            raise SandboxError(f'{r} belongs to the acceptance checks and is read only: change the code, not the check')
        if self.claims is not None:
            owner = self.claims.setdefault(r, self.name)
            if owner != self.name:
                raise SandboxError(f'{r} is being written by the task "{owner}" of this batch: leave it alone')
        return p

    def check_command(self, command):
        if not self.allow_run:
            raise SandboxError('this task may not run commands')
        parts, targets = split_command(command)
        if not parts:
            raise SandboxError('empty command')
        for part in parts:
            if denied(part):
                raise SandboxError(f'command refused by the safety list: {part[:80]}')
            if not any(r.search(part) for r in self.allow_run):
                raise SandboxError(f'command not in the allow list of this task: {part[:80]}')
        for target in targets:
            if target in ('', '1', '2', '/dev/null', '/dev/stdout', '/dev/stderr'):
                continue
            if any(c in target for c in '$*?~'):
                raise SandboxError(f'redirection to a computed path is not allowed: {target[:60]}')
            self.writable(target)


# the operating system sandbox ------------------------------------------------------------------
_jail = None


def _sandbox_profile():
    """Return normalized sandbox profile: 'secure', 'compatible', or 'trusted'."""
    raw = os.environ.get('TANDEM_SANDBOX', 'auto').strip().lower()
    if raw in ('secure', 'require'):
        return 'secure'
    if raw in ('compatible', 'auto', ''):
        return 'compatible'
    if raw in ('trusted', 'off'):
        return 'trusted'
    raise SandboxError(f'unknown TANDEM_SANDBOX profile {raw!r} (use secure, compatible, or trusted)')


def jail_available():
    """True when bubblewrap is installed and may create its namespaces on this machine."""
    global _jail
    profile = _sandbox_profile()
    if profile == 'trusted':
        return False
    if _jail is None:
        exe = shutil.which('bwrap')
        _jail = False
        if exe:
            try:
                _jail = subprocess.run(jail_command('true', '/tmp'),
                                       capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _jail = False
    if not _jail and profile == 'secure':
        raise SandboxError('TANDEM_SANDBOX=secure/require but bubblewrap is not usable on this machine')
    return _jail


def _socket_masks(base='/run', depth=3):
    """Mounts that hide the Unix sockets of the host from the sandbox. A socket on the file system
    stays reachable through a read only bind and without a network: the session bus, the Docker
    socket, the key agents. The per user runtime folders are replaced by empty ones, every other
    socket under /run is covered by /dev/null."""
    args, users = [], os.path.join(base, 'user')
    if os.path.isdir(users) and not os.path.islink(users):
        args += ['--tmpfs', users]
    stack = [(base, 0)]
    while stack:
        folder, level = stack.pop()
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.path == users or entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if level + 1 < depth:
                        stack.append((entry.path, level + 1))
                elif stat.S_ISSOCK(entry.stat(follow_symlinks=False).st_mode):
                    args += ['--ro-bind', '/dev/null', entry.path]
            except OSError:
                continue
    return args


def skip_dirs(root):
    """Folders of a workspace that stamp() does not enter (generated folders), as relative paths."""
    out, stack = set(), [(os.fspath(root), '')]
    while stack:
        dirpath, prefix = stack.pop()
        try:
            with os.scandir(dirpath) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            if entry.name in SKIP_DIRS:
                out.add(f'{prefix}{entry.name}')
            else:
                stack.append((entry.path, f'{prefix}{entry.name}/'))
    return out


def jail_command(command, root, allow_net=False):
    """The bubblewrap call that runs `command` with only `root` writable and host $HOME hidden."""
    root = Path(root).resolve()
    home = Path.home().resolve()
    args = ['bwrap', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp', '--tmpfs', '/run']
    if allow_net or os.environ.get('TANDEM_SANDBOX_NET', '') == '1':
        if os.path.isdir('/run/systemd/resolve') and not os.path.islink('/run/systemd/resolve'):
            args += ['--ro-bind', '/run/systemd/resolve', '/run/systemd/resolve']
    for sys_dir in ('/usr', '/bin', '/sbin', '/lib', '/lib64', '/lib32', '/etc', '/opt', '/nix'):
        if os.path.islink(sys_dir):
            args += ['--symlink', os.readlink(sys_dir), sys_dir]
        elif os.path.isdir(sys_dir):
            args += ['--ro-bind', sys_dir, sys_dir]
    args += ['--tmpfs', str(home), '--setenv', 'HOME', str(home)]
    base_prefix = str(Path(sys.base_prefix).resolve())
    if base_prefix != '/usr' and not base_prefix.startswith('/usr/') and os.path.isdir(base_prefix):
        args += ['--ro-bind', base_prefix, base_prefix]
    args += ['--bind', str(root), str(root)]
    skip_mounts = []
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        keep = []
        for d in sorted(dirnames):
            dp = Path(dirpath) / d
            if dp.is_symlink():
                continue
            if d in SKIP_DIRS:
                skip_mounts.append(str(dp))
            else:
                keep.append(d)
        dirnames[:] = keep
    for m in skip_mounts:
        args += ['--ro-bind', m, m]
    if not allow_net and os.environ.get('TANDEM_SANDBOX_NET', '') != '1':
        args += ['--unshare-net']
    return args + ['--unshare-pid', '--unshare-ipc', '--die-with-parent', '--new-session', '--chdir', str(root), '/bin/sh', '-c', command]


def clean_env(strip_secrets=True):
    """Build a subprocess environment, stripping API keys and credentials when strip_secrets is True."""
    if not strip_secrets:
        return {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def describe_jail():
    profile = _sandbox_profile()
    if profile == 'trusted':
        return 'WARNING: command text checks only (TANDEM_SANDBOX=trusted/off; bubblewrap disabled)'
    try:
        if jail_available():
            net = 'network allowed' if os.environ.get('TANDEM_SANDBOX_NET', '') == '1' else 'no network'
            return f'bubblewrap (allowlist system dirs, home hidden, workspace writable, env secrets stripped, {net})'
    except SandboxError as exc:
        return f'ERROR: {exc}'
    return 'WARNING: bubblewrap unavailable: falling back to unjailed command text checks only (outbound symlinks refused; set TANDEM_SANDBOX=require or secure to fail closed)'


def outbound_symlinks(root):
    """Symlinks under root whose resolved target lies outside root. SKIP_DIRS skipped."""
    root = Path(root).resolve()
    out, stack = [], [root]
    while stack:
        folder = stack.pop()
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    target = Path(entry.path).resolve()
                    if target != root and root not in target.parents:
                        out.append(str(Path(entry.path).relative_to(root)))
                elif entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS:
                    stack.append(Path(entry.path))
            except OSError:
                continue
    return sorted(out)


def _run_output_cap():
    try:
        return max(65536, int(os.environ.get('TANDEM_RUN_OUTPUT_CAP', 2 * 1024 * 1024)))
    except ValueError:
        return 2 * 1024 * 1024


def _run_timeout(default=180):
    try:
        return max(1, int(os.environ.get('TANDEM_RUN_TIMEOUT', default)))
    except ValueError:
        return default


def _log_cap(default=64 * 1024 * 1024):
    try:
        return max(65536, int(os.environ.get('TANDEM_LOG_CAP', default)))
    except ValueError:
        return default


def run(command, cwd, timeout=None, jail=False, allow_net=False, strip_env=None, max_output_bytes=None,
        guard_symlinks=True, log_path=None, log_cap_bytes=None):
    """Run a shell command, return (exit code, combined output). jail=True runs it inside the
    operating system sandbox when there is one. Output kept in RAM is bounded to avoid OOM."""
    # no bytecode files: a check run just before an edit must not leave a stale .pyc behind
    if timeout is None:
        timeout = _run_timeout()
    if strip_env is None:
        strip_env = bool(jail)
    env = clean_env(strip_secrets=strip_env)
    profile = _sandbox_profile()
    use_jail = bool(jail and jail_available())
    if jail and not use_jail and profile == 'secure':
        raise SandboxError('TANDEM_SANDBOX=secure/require but bubblewrap is not usable on this machine')
    if not use_jail and guard_symlinks and os.environ.get('TANDEM_ALLOW_OUTBOUND_SYMLINKS', '') != '1':
        offenders = outbound_symlinks(cwd)
        if offenders:
            raise SandboxError('workspace has symlinks pointing outside it (' + ', '.join(offenders[:5]) +
                               '): a command could write through them. Remove them, use bubblewrap, '
                               'or set TANDEM_ALLOW_OUTBOUND_SYMLINKS=1')

    cap = _run_output_cap() if max_output_bytes is None else max(4096, int(max_output_bytes))
    head_cap = max(1024, cap // 4)
    tail_cap = max(0, cap - head_cap)
    popen_kw = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env)
    if os.name == 'posix':
        popen_kw['start_new_session'] = True
    if use_jail:
        proc = subprocess.Popen(jail_command(command, cwd, allow_net=allow_net), **popen_kw)
    else:
        proc = subprocess.Popen(command, shell=True, cwd=str(cwd), **popen_kw)

    head, tail = [], collections.deque()
    head_kept = tail_kept = total = 0
    buf_lock = threading.Lock()
    log_cap = _log_cap() if log_cap_bytes is None else max(4096, int(log_cap_bytes))
    log_fh = open(log_path, 'wb') if log_path is not None else None
    log_written = 0

    def _drain():
        nonlocal head_kept, tail_kept, total, log_written
        assert proc.stdout is not None
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            if log_fh is not None and log_written < log_cap:
                take_log = chunk[:log_cap - log_written]
                try:
                    log_fh.write(take_log)
                    log_written += len(take_log)
                except OSError:
                    pass
            with buf_lock:
                total += len(chunk)
                if head_kept < head_cap:
                    take = chunk[:head_cap - head_kept]
                    head.append(take)
                    head_kept += len(take)
                    chunk = chunk[len(take):]
                    if not chunk:
                        continue
                if tail_cap > 0:
                    tail.append(chunk)
                    tail_kept += len(chunk)
                    while tail_kept > tail_cap:
                        old = tail[0]
                        excess = tail_kept - tail_cap
                        if excess >= len(old):
                            tail.popleft()
                            tail_kept -= len(old)
                        else:
                            tail[0] = old[excess:]
                            tail_kept -= excess

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == 'posix':
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        else:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    reader.join(timeout=2)
    with buf_lock:
        head_b = b''.join(head)
        tail_b = b''.join(tail)
        hk, tk, tot = head_kept, tail_kept, total
    if not reader.is_alive() and proc.stdout is not None:
        try:
            proc.stdout.close()
        except OSError:
            pass
    if log_fh is not None:
        try:
            if tot > log_written:
                log_fh.write(f'\n[log truncated: {tot} bytes total, kept {log_written} bytes]\n'.encode('utf-8'))
            log_fh.close()
        except OSError:
            pass

    text = head_b.decode('utf-8', errors='replace')
    if tot > hk + tk:
        text += f'\n[output truncated: {tot} bytes total, kept first {hk} and last {tk} bytes]\n'
    text += tail_b.decode('utf-8', errors='replace')
    if timed_out:
        return 124, text + f'\n[timeout after {timeout} s]'
    return (proc.returncode if proc.returncode is not None else 124), text


# reading ---------------------------------------------------------------------------------------
def cut_note(path, limit=4_000_000):
    """A note when read_text() gave only the start of a file, '' otherwise."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return ''
    if path.suffix.lower() == '.pdf' or size <= limit:
        return ''
    return f'NOTE: the file has {size} bytes, only the first {limit} were read: narrow it or split it.'


def read_text(path, limit=4_000_000):
    """Text of a file; PDFs through pdftotext when it is installed."""
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        try:
            done = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, text=True, timeout=120,
                                  errors='replace')
        except (OSError, subprocess.SubprocessError) as exc:
            raise SandboxError('cannot read the PDF (pdftotext missing or failed)') from exc
        if done.returncode != 0:
            raise SandboxError('cannot read the PDF (pdftotext failed)')
        return done.stdout[:limit]
    with path.open('rb') as f:
        data = f.read(limit)
    if b'\x00' in data[:4096]:
        raise SandboxError(f'{path.name} looks like a binary file')
    return data.decode('utf-8', errors='replace')


def walk(root, glob='**/*', limit=None):
    """Files under root that match the glob, generated folders and symlinks skipped."""
    root = Path(root)
    out = []
    match_base = '/' not in _strip_rel_prefix(glob)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not (Path(dirpath) / d).is_symlink()]
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                continue
            rel = str(p.relative_to(root))
            if glob_match(rel, glob, match_basename=match_base):
                out.append(rel)
                if limit is not None and len(out) >= limit:
                    return sorted(out)
    return sorted(out)


_STAMP_LOCK = threading.Lock()
_STAMP_CACHE: dict[str, dict[str, tuple]] = {}


def stamp(root, limit=None):
    """Size and SHA-256 of the files of a workspace, to see what a command touched.

    Uses os.scandir and a ctime_ns fast-path: ctime_ns cannot be spoofed from userspace,
    so unchanged (size, mtime_ns, ctime_ns, ino, mode) safely reuses the cached SHA-256.
    """
    root_key = os.fspath(root)
    if os.name == 'posix':
        with _STAMP_LOCK:
            prev_cache = _STAMP_CACHE.get(root_key, {})
    else:
        prev_cache = {}
    new_cache = {}
    out = {}
    stack = [(root_key, '')]
    while stack:
        dirpath, prefix = stack.pop()
        try:
            with os.scandir(dirpath) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    if entry.name not in SKIP_DIRS:
                        out[f'{prefix}{entry.name}'] = (-1, 'symlink:' + os.readlink(entry.path), 0)
                        if limit is not None and len(out) >= limit:
                            return out
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in SKIP_DIRS:
                        stack.append((entry.path, f'{prefix}{entry.name}/'))
                elif entry.is_file(follow_symlinks=False):
                    rel = f'{prefix}{entry.name}'
                    st = entry.stat(follow_symlinks=False)
                    mode = stat.S_IMODE(st.st_mode)
                    meta = (st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, mode)
                    cached = prev_cache.get(rel)
                    if cached is not None and cached[:5] == meta:
                        digest_hex = cached[5]
                    else:
                        with open(entry.path, 'rb') as f:
                            digest_hex = hashlib.file_digest(f, 'sha256').hexdigest()
                    new_cache[rel] = (*meta, digest_hex)
                    out[rel] = (st.st_size, digest_hex, mode)
                    if limit is not None and len(out) >= limit:
                        return out
            except OSError:
                continue
    if limit is None and os.name == 'posix':
        with _STAMP_LOCK:
            _STAMP_CACHE.pop(root_key, None)
            _STAMP_CACHE[root_key] = new_cache
            while len(_STAMP_CACHE) > 8:
                _STAMP_CACHE.pop(next(iter(_STAMP_CACHE)))
    return out
