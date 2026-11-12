"""What the executor may touch: paths inside a workspace, commands that match an allow list.

Two layers guard the commands the executor chooses. The first is a check of the command text:
every part of a pipeline or a chain must match the allow list, none may match the safety list,
command substitution is refused and a redirection must point at a writable file. The second,
where bubblewrap is installed, is an operating system sandbox: the whole machine is read only,
only the workspace is writable, credentials folders are hidden and there is no network."""
import fnmatch
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

# Never run for the executor, whatever the allow list says.
DENY = [r'\bsudo\b', r'\bsu\b\s', r'\bdoas\b', r'\brm\s+(-\w*\s+)*-\w*r\w*\s+(/|~|\$HOME)(\s|$)',
        r'\bgit\s+(push|commit|reset|clean|checkout|rebase|merge|tag|restore|stash|config|remote)\b',
        r'\bmkfs', r'\bdd\s+if=', r'\bshutdown\b', r'\breboot\b', r'\bcurl\b.*\|\s*(ba)?sh', r'\bwget\b.*\|\s*(ba)?sh',
        r'\bchown\b', r'\bchmod\s+-R\b', r'>\s*/dev/sd', r'\bsystemctl\b', r'\bkill(all)?\b', r'\bpkill\b', r'\bssh\b', r'\bscp\b',
        r'\brsync\b', r'\bnc\b', r'\bnpm\s+publish\b', r'\bpip3?\s+install\b', r'\bapt(-get)?\b', r'\bcrontab\b',
        r'\beval\b', r'\bexec\b', r'\bsource\b']
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'managed_components', '.history', 'dist', '.cache'}
SECRETS = ['.ssh', '.gnupg', '.aws', '.azure', '.kube', '.docker', '.config/gh', '.config/gcloud', '.password-store',
           '.netrc', '.git-credentials', '.npmrc', '.pypirc']
TEST_DIR = re.compile(r'^(tests?|specs?|__tests__)$', re.I)


class SandboxError(RuntimeError):
    pass


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
    def __init__(self, root, write_globs=None, allow_run=None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise SandboxError(f'workspace is not a folder: {root}')
        if self.root == Path(self.root.anchor) or self.root == Path.home().resolve():
            raise SandboxError('workspace must be a project folder, not / or the home folder')
        self.write_globs = [g for g in (write_globs or []) if g.strip()]
        try:
            self.allow_run = [re.compile(r) for r in (allow_run or []) if r.strip()]
        except re.error as exc:
            raise SandboxError(f'allow_run holds a bad regular expression: {exc}') from exc
        self.protected = set()             # files and folders the acceptance checks rely on
        self.claims = None                 # shared {path: task name} when tasks run side by side
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
        return any(fnmatch.fnmatch(r, g) for g in self.write_globs)

    def is_protected(self, r):
        parts = Path(r).parts
        return any(str(Path(*parts[:k])) in self.protected for k in range(1, len(parts) + 1))

    def protect(self, verify_commands):
        """Files named by the acceptance checks (and test folders) become read only for the
        executor, unless a write glob names them: a check must not be bent to pass."""
        for command in verify_commands:
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
        return sorted(self.protected)

    def writable(self, rel):
        p = self.path(rel)
        if p == self.root:
            raise SandboxError('that is the workspace folder, not a file')
        r = self.rel(p)
        if '.git' in Path(r).parts:
            raise SandboxError('the .git folder is not writable')
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
            for pattern in DENY:
                if re.search(pattern, part):
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


def jail_available():
    """True when bubblewrap is installed and may create its namespaces on this machine."""
    global _jail
    mode = os.environ.get('TANDEM_SANDBOX', 'auto').lower()
    if mode == 'off':
        return False
    if _jail is None:
        exe = shutil.which('bwrap')
        _jail = False
        if exe:
            try:
                _jail = subprocess.run([exe, '--ro-bind', '/', '/', '--unshare-net', '--unshare-pid', '--die-with-parent', 'true'],
                                       capture_output=True, timeout=10).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _jail = False
    if not _jail and mode == 'require':
        raise SandboxError('TANDEM_SANDBOX=require but bubblewrap is not usable on this machine')
    return _jail


def jail_command(command, root):
    """The bubblewrap call that runs `command` with only `root` writable."""
    root = Path(root).resolve()
    home = Path.home().resolve()
    args = ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp']
    for name in SECRETS:
        secret = home / name
        if root == secret or secret in root.parents:
            continue
        if secret.is_dir():
            args += ['--tmpfs', str(secret)]
        elif secret.is_file():
            args += ['--ro-bind', '/dev/null', str(secret)]
    args += ['--bind', str(root), str(root)]
    if (root / '.git').is_dir():
        args += ['--ro-bind', str(root / '.git'), str(root / '.git')]
    if os.environ.get('TANDEM_SANDBOX_NET', '') != '1':
        args += ['--unshare-net']
    return args + ['--unshare-pid', '--die-with-parent', '--new-session', '--chdir', str(root), '/bin/sh', '-c', command]


def describe_jail():
    try:
        if jail_available():
            net = 'network allowed' if os.environ.get('TANDEM_SANDBOX_NET', '') == '1' else 'no network'
            return f'bubblewrap (machine read only, workspace writable, credentials hidden, {net})'
    except SandboxError as exc:
        return str(exc)
    return 'command text checks only (bubblewrap not available or TANDEM_SANDBOX=off)'


def run(command, cwd, timeout=180, jail=False):
    """Run a shell command, return (exit code, combined output). jail=True runs it inside the
    operating system sandbox when there is one."""
    # no bytecode files: a check run just before an edit must not leave a stale .pyc behind
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    try:
        if jail and jail_available():
            done = subprocess.run(jail_command(command, cwd), capture_output=True, text=True, timeout=timeout, errors='replace',
                                  stdin=subprocess.DEVNULL, env=env)
        else:
            done = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                                  errors='replace', stdin=subprocess.DEVNULL, env=env)
        return done.returncode, (done.stdout or '') + (('\n' + done.stderr) if done.stderr else '')
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b'')
        partial = partial.decode(errors='replace') if isinstance(partial, bytes) else partial
        return 124, partial + f'\n[timeout after {timeout} s]'


# reading ---------------------------------------------------------------------------------------
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


def walk(root, glob='**/*', limit=4000):
    """Files under root that match the glob, generated folders skipped."""
    root = Path(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            rel = str((Path(dirpath) / name).relative_to(root))
            if fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(name, glob):
                out.append(rel)
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)


def stamp(root, limit=6000):
    """Modification time and size of the files of a workspace, to see what a command touched."""
    root = Path(root)
    out = {}
    for rel in walk(root, '*', limit):
        try:
            st = (root / rel).stat()
        except OSError:
            continue
        out[rel] = (st.st_mtime_ns, st.st_size)
    return out
