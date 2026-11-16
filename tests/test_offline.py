"""Checks that need no model: sandbox limits, evidence check, journal and rollback, parsing."""
import json
import os
import sys
import tempfile
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_STRICT'] = '0'             # the loose contract; the strict one is checked in its own section
from tandem_mcp import agent, digest, engine, sandbox, store  # noqa: E402

checks = 0


def ok(cond, what):
    global checks
    assert cond, what
    checks += 1


def refused(fn, *args):
    try:
        fn(*args)
    except sandbox.SandboxError:
        return True
    return False


# paths and write limits ------------------------------------------------------------------------
root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(root / 'src').mkdir()
(root / 'tests').mkdir()
(root / 'src/a.txt').write_text('alpha\nbeta 42 mV\ngamma\n')
(root / 'tests/test_a.py').write_text('assert True\n')
(root / 'check.sh').write_text('true\n')
ws = sandbox.Workspace(root, ['src/*.txt'], [r'^make\b'])
ok(refused(ws.path, '../outside'), 'path escape')
ok(refused(ws.path, '/etc/passwd'), 'absolute path outside')
ok(refused(ws.writable, 'README.md'), 'write outside the globs')
ok(refused(ws.writable, '.git/config'), 'write into .git')
ok(refused(ws.writable, 'src/../.git/config'), 'write into .git through ..')
ok(refused(ws.writable, 'src/deep/er/n.txt'), 'src/*.txt does not match deeper subdirectories')
ok(sandbox.glob_match('src/a.py', 'src/*.py') and not sandbox.glob_match('src/sub/a.py', 'src/*.py'), 'path-aware glob')
ok(sandbox.glob_match('src/sub/a.py', 'src/**/*.py'), 'double-star glob matches subdirectories')
imm = sandbox.Workspace(root, ['src/**/*.txt'], immutable=['src/a.txt'])
ok(refused(imm.writable, 'src/a.txt') and imm.writable('src/b.txt').name == 'b.txt', 'explicit immutable overrides write_globs')
os.symlink('/etc', root / 'src/link')
ok(refused(ws.path, 'src/link/passwd'), 'symlink that leaves the workspace')
(root / 'src/link').unlink()
ok(refused(sandbox.Workspace, '/'), 'root as a workspace')
ok(refused(sandbox.Workspace, str(Path.home())), 'home as a workspace')
ok(refused(sandbox.Workspace, root, [], ['(']), 'bad regular expression in allow_run')

# commands --------------------------------------------------------------------------------------
ok(refused(ws.check_command, 'ls'), 'command not allowed')
ok(refused(ws.check_command, 'make && sudo rm x'), 'sudo refused even when the allow list matches')
ok(refused(ws.check_command, 'make; git push'), 'git push refused')
ok(refused(ws.check_command, 'make test; cat ~/.ssh/id_rsa'), 'a chained command must match the allow list too')
ok(refused(ws.check_command, 'make test | sh'), 'a pipe target must match the allow list too')
ok(refused(ws.check_command, 'make test\ncat /etc/passwd'), 'a second line must match the allow list too')
ok(refused(ws.check_command, 'make test & cat /etc/passwd'), 'a background command must match too')
ok(refused(ws.check_command, 'make $(cat /etc/passwd)'), 'command substitution')
ok(refused(ws.check_command, 'make `id`'), 'backtick substitution')
ok(refused(ws.check_command, 'make "$(id)"'), 'substitution inside double quotes')
ok(refused(ws.check_command, 'make <(id)'), 'process substitution')
ok(refused(ws.check_command, 'make > /etc/cron.d/x'), 'redirection outside the workspace')
ok(refused(ws.check_command, 'make > README.md'), 'redirection outside the write globs')
ok(refused(ws.check_command, 'make > $HOME/x'), 'redirection to a computed path')
ok(refused(ws.check_command, 'make "unbalanced'), 'unbalanced quote')
ok(refused(ws.check_command, ''), 'empty command')
for fine in ('make test', 'make test 2>&1', 'make test > src/out.txt', 'make test >/dev/null 2>&1', "make ARG='a;b|c' test",
             'make test && make lint', 'make "x > y"'):
    ws.check_command(fine)
    checks += 1
ok(refused(sandbox.Workspace(root).check_command, 'make'), 'no allow list: no command')
parts, targets = sandbox.split_command("a 'x;y' && b \"p|q\" | c >> out.txt; d")
ok(parts == ["a 'x;y'", 'b "p|q"', 'c >> out.txt', 'd'] and targets == ['out.txt'], 'command split respects quotes')

# files of the checks -----------------------------------------------------------------------------
free = sandbox.Workspace(root)
locked = free.protect(['python3 tests/test_a.py', 'sh check.sh && pytest -q tests', 'make -C src'])
ok(locked == ['check.sh', 'tests', 'tests/test_a.py'], 'files and test folders named by the checks are protected')
ok(refused(free.writable, 'tests/test_a.py') and refused(free.writable, 'tests/new_test.py') and refused(free.writable, 'check.sh'),
   'protected files are read only')
ok(free.writable('src/a.txt') and free.writable('src/b.txt'), 'a folder that is only passed to a tool stays writable')
auto_ws = sandbox.Workspace(root)
auto_locked = auto_ws.protect(['pytest -q'])
ok('tests' in auto_locked and refused(auto_ws.writable, 'tests/test_a.py'), 'test runner auto-protects test directories')
named = sandbox.Workspace(root, ['tests/*.py', 'src/*'])
named.protect(['python3 tests/test_a.py'])
ok(named.writable('tests/test_a.py'), 'a write glob that names the check file unlocks it')
shared = {}
one, two = sandbox.Workspace(root), sandbox.Workspace(root)
one.claims = two.claims = shared
one.name, two.name = 'one', 'two'
ok(one.writable('src/a.txt') and refused(two.writable, 'src/a.txt') and two.writable('src/b.txt'), 'file ownership inside a batch')

# the operating system sandbox --------------------------------------------------------------------
if sandbox.jail_available():
    outside = Path.home() / f'.tandem-test-{os.getpid()}'
    code, out = sandbox.run(f'touch {outside}; echo inside > made.txt; cat made.txt', root, jail=True)
    ok(not outside.exists() and 'inside' in out and (root / 'made.txt').exists(), 'jail: workspace writable, home read only')
    (root / '.git').mkdir(exist_ok=True)
    sandbox.run('touch .git/hook', root, jail=True)
    ok(not (root / '.git/hook').exists(), 'jail: .git read only')
    import socket
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    probe = ('python3 -c "import socket; s = socket.socket(); s.settimeout(3); '
             f'print(\'reach\', s.connect_ex((\'127.0.0.1\', {listener.getsockname()[1]})))"')
    ok(sandbox.run(probe, root, guard_symlinks=False)[1].split()[-1] == '0', 'without the jail the host port is reachable')
    ok(sandbox.run(probe, root, jail=True)[1].split()[-1] != '0', 'jail: no network, not even the loopback of the host')
    listener.close()
    if (Path.home() / '.ssh').is_dir() and Path.home() not in root.parents:
        code, out = sandbox.run('ls -A ~/.ssh | wc -l', root, jail=True)
        ok(out.strip() == '0', 'jail: credentials folder hidden')
    os.environ['TANDEM_TEST_API_KEY'] = 'super-secret-value'
    code, out = sandbox.run('python3 -c "import os; print(os.environ.get(\'TANDEM_TEST_API_KEY\', \'MISSING\'))"', root, jail=True)
    ok(out.strip() == 'MISSING', 'jail: secret env vars are stripped')
    del os.environ['TANDEM_TEST_API_KEY']
    print('jail checks ran')
else:
    print('jail checks skipped (bubblewrap not usable here)')

# evidence ----------------------------------------------------------------------------------------
lines = (root / 'src/a.txt').read_text().splitlines()
good, bad = digest.check_evidence([{'line': 2, 'quote': 'beta 42 mV'}, {'line': 1, 'quote': 'gamma'},
                                   {'line': 2, 'quote': 'beta 43 mV'}, {'line': 9, 'quote': ''}, 'junk',
                                   {'line': '2', 'quote': '2| beta 42'}, {'line': 1, 'quote': 'alpha beta'}], lines)
ok(len(good) == 4 and bad == 3, 'four quotes stand, three fall')
ok(good[1]['line'] == 3, 'a right quote with a wrong line number is corrected')
ok(digest.check_evidence('not a list', lines) == ([], 0), 'evidence that is not a list')
ok(digest.agreement(['Yes', ' yes ', 'no'])[0] == 2 / 3, 'agreement of text answers')
ok(digest.agreement([{'a': 1}, {'a': 1}])[0] == 1.0, 'agreement of structured answers')
body, hits = digest.prefilter('one\ntwo\nthree\nfour\nfive', 'thr', context=1)
ok(hits == 3 and body.startswith('2| two'), 'prefilter keeps context and line numbers')
source = 'VDD is 3.30 V\nlimit 1,500 mA at 85 C\nrev 12\n'
ok(digest.loose_numbers('VDD is 3.30 V, limit 1500 mA at 85 C, margin 17 %, 4 items', source) == ['17'],
   'a number that is not in the source is listed, small counts are not')
ok(digest.loose_numbers('see line 42, at 85 C', source, evidence=[{'line': 42}]) == [], 'line references are not figures')
ok(digest.loose_values({'vdd': 3.3, 'part': 'ESP32', 'rev': 12, 'rows': [{'t': '85 C', 'ok': True, 'x': None}]}, source) == ['ESP32'],
   'an extracted value that is not in the source is listed')
parts = digest.chunks(digest.numbered('x' * 50 + '\n' + 'y' * 50 + '\n' + 'z' * 50), 70)
ok(len(parts) == 3 and parts[1].startswith('2| '), 'chunks split on lines and keep the numbers')
trunc_parts, trunc_count = digest.chunk_with_stats('1| ' + 'a' * 2500, 3000)
ok(trunc_count == 1 and 'truncated' in trunc_parts[0], 'long line truncation is signaled')
sup_ok = digest.check_claim_support('VDD is 3.30 V', [{'line': 1, 'quote': 'VDD is 3.30 V'}], ['VDD is 3.30 V'])
ok(sup_ok['quote_found'] and sup_ok['claim_supported'] == 'quote_only', 'quote_found is distinct from semantic proof')
sup_bad = digest.check_claim_support('VDD is not 3.30 V', [{'line': 1, 'quote': 'VDD is 3.30 V'}], ['VDD is 3.30 V'])
ok(sup_bad['quote_found'] and sup_bad['claim_supported'] == 'contested' and sup_bad['warnings'], 'polarity mismatch flagged')

# what models print -------------------------------------------------------------------------------
ok(engine.strip_think('<think>plan</think>\nanswer') == 'answer', 'reasoning block removed')
ok(engine.strip_think('plan without opening tag</think>answer') == 'answer', 'reasoning with a swallowed opening tag')
ok(engine.strip_think('<think>never closed') == '', 'unfinished reasoning is not an answer')
ok(engine.strip_think('plain <b>text</b>') == 'plain <b>text</b>', 'other tags stay')
ok(engine.parse_json('Sure:\n```json\n{"a": [1, 2]}\n```\nDone') == {'a': [1, 2]}, 'JSON inside a fence and prose')
ok(engine.parse_json('<think>{"no": 1}</think>{"yes": 2}') == {'yes': 2}, 'JSON after the reasoning, not inside it')
ok(engine.parse_json('no json here') is None and engine.parse_json('{"a": 1}', (list,)) is None, 'no JSON, or the wrong kind')
schema = {'type': 'object', 'required': ['a'], 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'string'}}}
ok(engine.problem({'a': 1}, schema) == '' and 'missing' in engine.problem({}, schema) and 'type' in engine.problem({'a': 'x'}, schema)
   and engine.problem([], schema) and engine.problem({'a': True}, schema), 'schema problems are named')
nested_schema = {'type': 'object', 'required': ['items'], 'additionalProperties': False,
                 'properties': {'items': {'type': 'array', 'items': {'type': 'object', 'required': ['id'], 'properties': {'id': {'type': 'integer', 'minimum': 1}}}}}}
ok(engine.problem({'items': [{'id': 2}]}, nested_schema) == ''
   and engine.problem({'items': [{'id': 0}]}, nested_schema)
   and engine.problem({'items': [{'id': 1}], 'extra': 1}, nested_schema), 'nested schema validation')
ok(agent.text_call('{"tool": "read_file", "args": {"path": "a"}}') == ('read_file', {'path': 'a'}), 'tool call as a JSON reply')
ok(agent.text_call('<tool_call>\n{"name": "run", "arguments": {"command": "make"}}\n</tool_call>') == ('run', {'command': 'make'}),
   'tool call printed by a chat template')
ok(agent.text_call('{"name": "run", "arguments": "{\\"command\\": \\"make\\"}"}') == ('run', {'command': 'make'}),
   'tool call with arguments as a string')
ok(agent.text_call('I will read the file now.') is None, 'prose is not a tool call')
ok(agent.text_call('finish(summary="Fixed it.", blocked=False)') == ('finish', {'summary': 'Fixed it.', 'blocked': False}),
   'tool call written as a function call')
ok(agent.text_call('```python\nread_file("calc.py", start=3)\n```') == ('read_file', {'path': 'calc.py', 'start': 3}),
   'function call with a positional argument, in a fence')
ok(agent.text_call('__import__("os").system("id")') is None and agent.text_call('run(command=open("/etc/passwd").read())') is None
   and agent.text_call('finish(') is None, 'only literal arguments of a known tool are read, nothing is run')

# syntax of changed files -------------------------------------------------------------------------
for name, text, verdict in (('g.py', 'x = 1\n', ''), ('b.py', 'def f(:\n', 'bad'), ('g.json', '{"a": 1}', ''), ('b.json', '{a}', 'bad'),
                            ('g.toml', 'a = 1\n', ''), ('b.toml', 'a = \n', 'bad'), ('g.svg', '<svg/>', ''), ('b.xml', '<a>', 'bad'),
                            ('x.c', 'int main(', None)):
    (root / name).write_text(text)
    found = agent.syntax_of(root / name)
    ok(found == verdict if verdict in ('', None) else bool(found), f'syntax of {name}')

# journal, diff, rollback -------------------------------------------------------------------------
job, folder = store.new_job('delegate')
task = agent.Task(job, folder, 'goal', ws, [], 5, 0, '', '')
ok(task.call('replace_in_file', {'path': 'src/a.txt', 'old': 'beta 42 mV', 'new': 'beta 61 mV'}) == 'replaced', 'replace')
ok(task.call('replace_in_file', {'path': 'src/a.txt', 'old': 'nothing', 'new': 'x'}).startswith('ERROR'), 'replace needs one match')
ok(task.call('replace_in_file', {'path': 'src/none.txt', 'old': 'a', 'new': 'x'}).startswith('ERROR'), 'replace in a missing file')
ok(task.call('read_file', {}).startswith('ERROR: read_file needs'), 'missing argument is named')
ok(task.call('fly', {}).startswith('ERROR: unknown tool'), 'unknown tool')
task.call('write_file', {'path': 'src/new.txt', 'content': 'hello\n'})
ok(refused(task.call, 'write_file', {'path': 'src/deep/er/n.txt', 'content': 'hello\n'}), 'src/*.txt refuses deeper subdirectories')
ok(refused(task.call, 'write_file', {'path': 'other.md', 'content': 'x'}), 'write limit holds inside the task')
ok(refused(task.call, 'run', {'command': 'rm -rf src'}), 'run limit holds inside the task')
ok('2| beta 61 mV' in task.call('read_file', {'path': 'src/a.txt', 'start': 2, 'end': 2}), 'read a range, numbered')
ok('src/a.txt:2:' in task.call('search', {'pattern': r'\d+ mV', 'glob': '*.txt'}), 'search')
ok('61 mV' in task.diff() and task.changes()[0][:2] == ('src/a.txt', 'changed'), 'diff and change list')
task._save('unverified', 'done', [])
ok('src/a.txt' in agent.rollback(job), 'rollback names the files')
ok((root / 'src/a.txt').read_text().count('42 mV') == 1 and not (root / 'src/new.txt').exists(), 'rollback restores and removes')
ok(store.read_job(job)['state'] == 'rolled_back' and store.read_job('../x') is None, 'job state, and no path tricks in job ids')

# batches -----------------------------------------------------------------------------------------
T = lambda name, *after: {'name': name, 'after': list(after)}  # noqa: E731
ok(agent.plan([T('a'), T('b', 'a'), T('c', 'a'), T('d', 'b', 'c')]) == [['a'], ['b', 'c'], ['d']], 'waves of a batch')
ok(refused(agent.plan, [T('a', 'b'), T('b', 'a')]) and refused(agent.plan, [T('a', 'zz')]) and refused(agent.plan, [T('a'), T('a')]),
   'cycle, unknown dependency and duplicate name are refused')

# memory and ledger -------------------------------------------------------------------------------
scope = store.scope_of(root)
ok(store.add_lesson(scope, 'No em dashes.') and not store.add_lesson(scope, 'no em  dashes.'), 'lesson stored once')
store.add_lesson('*', 'Comments in English.')
ok([r['text'] for r in store.lessons(scope)] == ['No em dashes.', 'Comments in English.'], 'project and global lessons')
ok(store.lessons('/elsewhere')[0]['scope'] == '*' and len(store.lessons('/elsewhere')) == 1, 'another project sees only the global ones')
ok(store.drop_lesson(scope, 'em dashes') == 1, 'lesson removed')
store.log('digest_file', kind='result', bytes_in=3600, bytes_out=0)
ok(len(store.ledger(1)) == 1, 'ledger line')
key = store.cache_key('a', 'b')
store.cache_put(key, {'answer': 'x'})
ok(store.cache_get(key) == {'answer': 'x'} and store.cache_get(store.cache_key('a', 'c')) is None and
   store.cache_key('ab', '') != store.cache_key('a', 'b'), 'cache')
res = store.cleanup(cache_keep=0, jobs_keep=200)
ok(res['cache_removed'] >= 1 and store.cache_get(key) is None, 'retention cleanup trims cache')

# fail-closed TANDEM_SANDBOX=require -----------------------------------------------------------------
saved_jail = sandbox._jail
saved_mode = os.environ.get('TANDEM_SANDBOX')
try:
    sandbox._jail = False
    os.environ['TANDEM_SANDBOX'] = 'auto'
    ok('TANDEM_SANDBOX=require' in sandbox.describe_jail(), 'describe_jail warns on auto fallback')
    os.environ['TANDEM_SANDBOX'] = 'require'
    ok(refused(sandbox.jail_available), 'TANDEM_SANDBOX=require fails closed in jail_available')
    ok(refused(sandbox.run, 'echo hi', root, 5, True), 'TANDEM_SANDBOX=require fails closed in run(jail=True)')
finally:
    sandbox._jail = saved_jail
    if saved_mode is None:
        os.environ.pop('TANDEM_SANDBOX', None)
    else:
        os.environ['TANDEM_SANDBOX'] = saved_mode

# store.cleanup() preserves pending-rollback jobs --------------------------------------------------
pj, pfolder = store.new_job('delegate')
store.write_job(pj, {'state': 'unverified', 'accepted': None, 'changes': [['a.py', 'changed', 1, 0]], 'touched': []})
rj, rfolder = store.new_job('delegate')
store.write_job(rj, {'state': 'rolled_back', 'accepted': None, 'changes': [['a.py', 'changed', 1, 0]], 'touched': []})
store.cleanup(cache_keep=200, jobs_ttl_days=0, jobs_keep=0, preserve_pending=True)
ok(pfolder.exists() and not rfolder.exists(), 'cleanup preserves pending-rollback jobs and removes rolled_back jobs')
store.cleanup(cache_keep=200, jobs_ttl_days=0, jobs_keep=0, preserve_pending=False)
ok(not pfolder.exists(), 'cleanup(preserve_pending=False) removes pending jobs')

# adversarial security & rollback checks ----------------------------------------------------------
# 1. >6,000 files: take_snapshot and stamp cover all 6,150 files, and modifying #6,120 outside write_globs is reverted
big_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
for idx in range(6150):
    (big_root / f'f_{idx:04d}.txt').write_text(f'v{idx}\n')
big_ws = sandbox.Workspace(big_root, ['allowed.txt'], [r'^python3\b'])
big_job, big_folder = store.new_job('delegate')
big_task = agent.Task(big_job, big_folder, 'goal', big_ws, [], 5, 0, '', '')
big_task.take_snapshot()
snap_6k = store.read_json(big_folder / 'snapshot.json')
stamp_6k = sandbox.stamp(big_root)
ok(len(snap_6k) == 6150 and 'f_6120.txt' in snap_6k and len(stamp_6k) == 6150 and 'f_6120.txt' in stamp_6k,
   'snapshot and stamp cover >6,000 files')
res_6k = big_task.call('run', {'command': 'python3 -c "open(\'f_6120.txt\', \'w\').write(\'tampered\')"'})
ok('reverted' in res_6k and 'f_6120.txt' in res_6k and (big_root / 'f_6120.txt').read_text() == 'v6120\n',
   'modifying file #6,120 outside write_globs is caught and reverted')

# 2. content change with preserved st_size and st_mtime_ns is caught by stamp() and reverted
utime_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
target = utime_root / 'secret.txt'
target.write_text('AAAA')
st0 = target.stat()
utime_ws = sandbox.Workspace(utime_root, ['allowed.txt'], [r'^python3\b'])
utime_job, utime_folder = store.new_job('delegate')
utime_task = agent.Task(utime_job, utime_folder, 'goal', utime_ws, [], 5, 0, '', '')
cmd_utime = (f'python3 -c "import os; p=\'secret.txt\'; open(p,\'w\').write(\'BBBB\'); '
             f'os.utime(p, ns=({st0.st_atime_ns}, {st0.st_mtime_ns}))"')
res_utime = utime_task.call('run', {'command': cmd_utime})
ok('reverted' in res_utime and 'secret.txt' in res_utime and target.read_text() == 'AAAA',
   'content change with preserved st_size and st_mtime_ns is caught and reverted')

# 3. external symlink inside workspace is skipped by walk, search, take_snapshot, and not followed on rollback
ext_dir = Path(tempfile.mkdtemp())
ext_file = ext_dir / 'outside.txt'
ext_file.write_text('OUTSIDE_SECRET\n')
sym_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(sym_root / 'normal.txt').write_text('NORMAL_TEXT\n')
os.symlink(ext_file, sym_root / 'evil_link.txt')
sym_ws = sandbox.Workspace(sym_root, [], [r'^echo\b'])
sym_job, sym_folder = store.new_job('delegate')
sym_task = agent.Task(sym_job, sym_folder, 'goal', sym_ws, [], 5, 0, '', '')
sym_task.take_snapshot()
sym_snap = store.read_json(sym_folder / 'snapshot.json')
ok('evil_link.txt' not in sandbox.walk(sym_root) and 'evil_link.txt' not in sym_snap
   and 'OUTSIDE_SECRET' not in sym_task.call('search', {'pattern': 'OUTSIDE_SECRET', 'glob': '*'}),
   'external symlink skipped by walk, search, and take_snapshot')
# Even if a job record lists the symlink in journal/touched, rollback must not touch the external target
sym_task.journal['evil_link.txt'] = 'OVERWRITE_ATTEMPT'
store.write_json(sym_folder / 'journal.json', sym_task.journal)
sym_task._save('unverified', 'done', [])
agent.rollback(sym_job)
ok(ext_file.exists() and ext_file.read_text() == 'OUTSIDE_SECRET\n', 'rollback does not follow or unlink external symlink')

# 4. binary file overwritten via write_file is restored byte-for-byte identically by rollback()
bin_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
orig_bytes = b'\x00\xff\xfe\x80data'
(bin_root / 'blob.bin').write_bytes(orig_bytes)
bin_ws = sandbox.Workspace(bin_root)
bin_job, bin_folder = store.new_job('delegate')
bin_task = agent.Task(bin_job, bin_folder, 'goal', bin_ws, [], 5, 0, '', '')
bin_task.call('write_file', {'path': 'blob.bin', 'content': 'overwritten text\n'})
ok('[binary file changed: blob.bin]' in bin_task.diff(), 'diff emits short binary notice')
bin_task._save('unverified', 'done', [])
agent.rollback(bin_job)
ok((bin_root / 'blob.bin').read_bytes() == orig_bytes, 'binary file restored byte-for-byte identically by rollback')

# 5. _guard_files() guards >200 protected test files without a 200-file cap
guard_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(guard_root / 'tests').mkdir()
for idx in range(220):
    (guard_root / 'tests' / f'test_{idx:03d}.py').write_text(f'def test_{idx}():\n    assert True\n')
guard_ws = sandbox.Workspace(guard_root, ['src/*.py'], [r'^python3\b'])
guard_ws.protect(['pytest'])
guard_job, guard_folder = store.new_job('delegate')
guard_task = agent.Task(guard_job, guard_folder, 'goal', guard_ws, ['pytest'], 5, 0, '', '')
guard_task.take_guard()
ok(len(guard_task.guard) == 220 and 'tests/test_219.py' in guard_task.guard,
   '_guard_files() guards all 220 test files (>200)')
(guard_root / 'tests' / 'test_219.py').write_text('TAMPERED\n')
restored_guard = guard_task.restore_guard()
ok('tests/test_219.py' in restored_guard
   and (guard_root / 'tests' / 'test_219.py').read_text() == 'def test_219():\n    assert True\n',
   'restore_guard() restores guarded test file #219')

# 6. SKIP_DIRS are read-only in jail_command() and refused by Workspace.writable()
skip_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(skip_root / '.venv').mkdir()
(skip_root / '.venv' / 'keep.txt').write_text('keep')
(skip_root / 'node_modules').mkdir()
(skip_root / 'node_modules' / 'pkg.js').write_text('module.exports = 1;')
jcmd = sandbox.jail_command('true', skip_root)
jcmd_pairs = list(zip(jcmd, jcmd[1:]))
ok(('--ro-bind', str((skip_root / '.venv').resolve())) in jcmd_pairs
   and ('--ro-bind', str((skip_root / 'node_modules').resolve())) in jcmd_pairs,
   'jail_command() bind-mounts .venv and node_modules read-only')
skip_ws = sandbox.Workspace(skip_root)
try:
    skip_ws.writable('.venv/x')
    ok(False, 'writable() must refuse .venv')
except sandbox.SandboxError:
    ok(True, 'writable() refuses SKIP_DIRS when not in write_globs')
if sandbox.jail_available():
    jcode, _ = sandbox.run('touch .venv/x', skip_root, jail=True)
    ok(jcode != 0 and not (skip_root / '.venv' / 'x').exists(),
       'writing to .venv inside bwrap jail fails')

# 7. parallel run() claims & run_lock: second task modifying file claimed by first is reverted and refused
claim_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(claim_root / 'shared.txt').write_text('init\n')
shared_claims = {}
shared_run_lock = __import__('threading').Lock()
ws_a = sandbox.Workspace(claim_root, ['shared.txt'], [r'^python3\b'])
ws_a.claims, ws_a.name, ws_a.run_lock = shared_claims, 'task-a', shared_run_lock
ws_b = sandbox.Workspace(claim_root, ['shared.txt'], [r'^python3\b'])
ws_b.claims, ws_b.name, ws_b.run_lock = shared_claims, 'task-b', shared_run_lock
ja, fa = store.new_job('delegate')
jb, fb = store.new_job('delegate')
ta = agent.Task(ja, fa, 'goal', ws_a, [], 5, 0, '', '')
tb = agent.Task(jb, fb, 'goal', ws_b, [], 5, 0, '', '')
res_a = ta.call('run', {'command': 'python3 -c "open(\'shared.txt\', \'w\').write(\'from-a\\n\')"'})
ok(not res_a.startswith('ERROR') and shared_claims.get('shared.txt') == 'task-a',
   'task A claims shared.txt via run()')
res_b = tb.call('run', {'command': 'python3 -c "open(\'shared.txt\', \'w\').write(\'from-b\\n\')"'})
ok('owned by another task' in res_b and (claim_root / 'shared.txt').read_text() == 'from-a\n',
   'task B run() modifying file claimed by task A is reverted and refused')

# 8. _launch() records post_state.json on exception, and rollback() is cautious if post_state.json is missing on error
crash_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(crash_root / 'a.txt').write_text('before\n')
crash_ws = sandbox.Workspace(crash_root)
crash_job, crash_folder = store.new_job('delegate')
crash_task = agent.Task(crash_job, crash_folder, 'goal', crash_ws, [], 5, 0, '', '')
crash_task._save('running', '', [])


def _boom():
    crash_task.call('write_file', {'path': 'a.txt', 'content': 'during\n'})
    raise RuntimeError('simulated crash')


th = agent._launch(crash_task, _boom)
th.join(5)
ok((crash_folder / 'post_state.json').exists() and store.read_job(crash_job)['state'] == 'error',
   '_launch() records post_state.json on exception')
(crash_folder / 'post_state.json').unlink()
(crash_root / 'a.txt').write_text('user_edit\n')
rb_crash = agent.rollback(crash_job)
ok('skipped (no post-crash state recorded): a.txt' in rb_crash and (crash_root / 'a.txt').read_text() == 'user_edit\n',
   'rollback() cautiously skips modified file when error job has no post_state.json')

# MCP client installer script ---------------------------------------------------------------------
from scripts import install as mcp_install  # noqa: E402
import json as _json  # noqa: E402

fake_home = Path(tempfile.mkdtemp())
(fake_home / '.gemini/config').mkdir(parents=True)
cfg_file = fake_home / '.gemini/config/mcp_config.json'
cfg_file.write_text(_json.dumps({'mcpServers': {'lmstudio': {'command': 'old'}, 'other': {'command': 'keep'}}}))
res_inst = mcp_install.install_antigravity('tandem-mcp', '/usr/bin/python3', '/app/main.py',
                                           {'TANDEM_SANDBOX': 'require'}, replace_legacy=True, home=fake_home)
cfg_data = _json.loads(cfg_file.read_text())
ok('installed' in res_inst and 'lmstudio' not in cfg_data['mcpServers'] and 'other' in cfg_data['mcpServers']
   and cfg_data['mcpServers']['tandem-mcp']['env'] == {'TANDEM_SANDBOX': 'require'},
   'install_antigravity replaces legacy and preserves other servers')
res_un = mcp_install.uninstall_antigravity('tandem-mcp', home=fake_home)
cfg_data = _json.loads(cfg_file.read_text())
ok('removed' in res_un and 'tandem-mcp' not in cfg_data['mcpServers'] and 'other' in cfg_data['mcpServers'],
   'uninstall_antigravity removes tandem-mcp only')
ok(mcp_install.parse_env_pairs(['A=1', 'B=x=y']) == {'A': '1', 'B': 'x=y'}, 'parse_env_pairs handles = in values')

# 9. _guard_files() catches immutable file beyond 2,000 files and restore_guard() reverts it
imm_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
for i in range(2200):
    (imm_root / f'f_{i:04d}.txt').write_text('x\n')
(imm_root / 'z_immutable.txt').write_text('original\n')
imm_ws = sandbox.Workspace(imm_root, ['*'], [r'^python3\b'], immutable=['z_immutable.txt'])
imm_job, imm_folder = store.new_job('delegate')
imm_task = agent.Task(imm_job, imm_folder, 'goal', imm_ws, [], 5, 0, '', '')
imm_task.take_guard()
imm_task.take_snapshot()
ok('z_immutable.txt' in imm_task.guard, '_guard_files() catches immutable file beyond 2,000 files')
imm_task.call('run', {'command': 'python3 -c "open(\'z_immutable.txt\', \'w\').write(\'tampered\\n\')"'})
imm_task.restore_guard()
ok((imm_root / 'z_immutable.txt').read_text() == 'original\n',
   'immutable file beyond 2,000 files modified by run() is reverted')

# 10. nested SKIP_DIRS (e.g. frontend/node_modules) are --ro-binded in jail_command() and read-only under jail=True
nested_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(nested_root / 'frontend' / 'node_modules').mkdir(parents=True)
(nested_root / 'frontend' / 'node_modules' / 'pkg.js').write_text('module.exports = 1;\n')
njcmd = sandbox.jail_command('true', nested_root)
njcmd_pairs = list(zip(njcmd, njcmd[1:]))
ok(('--ro-bind', str((nested_root / 'frontend' / 'node_modules').resolve())) in njcmd_pairs,
   'jail_command() bind-mounts nested frontend/node_modules read-only')
if sandbox.jail_available():
    njcode, _ = sandbox.run('touch frontend/node_modules/x', nested_root, jail=True)
    ok(njcode != 0 and not (nested_root / 'frontend' / 'node_modules' / 'x').exists(),
       'writing to nested frontend/node_modules inside bwrap jail fails')

# 11. internal symlink deleted and replaced by a regular file via run() is restored as a symlink by rollback()
int_sym_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(int_sym_root / 'real.txt').write_text('target\n')
os.symlink('real.txt', int_sym_root / 'link.txt')
int_sym_ws = sandbox.Workspace(int_sym_root, ['*'], [r'^python3\b'])
int_sym_job, int_sym_folder = store.new_job('delegate')
int_sym_task = agent.Task(int_sym_job, int_sym_folder, 'goal', int_sym_ws, [], 5, 0, '', '')
int_sym_task.take_snapshot()
int_sym_task.call('run', {'command': 'python3 -c "import os; os.unlink(\'link.txt\'); open(\'link.txt\', \'w\').write(\'replaced\\n\')"'})
int_sym_task._record_post_state()
int_sym_task._save('unverified', 'done', [])
rb_sym = agent.rollback(int_sym_job)
ok((int_sym_root / 'link.txt').is_symlink() and os.readlink(int_sym_root / 'link.txt') == 'real.txt' and 'link.txt' in rb_sym,
   'internal symlink replaced by regular file via run() is restored as a symlink by rollback()')

# 12. symlink replaced by a directory during run(), then user adds link/importante.txt -> rollback() skips link and preserves it
dir_sym_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(dir_sym_root / 'target_dir').mkdir()
(dir_sym_root / 'target_dir' / 'base.txt').write_text('base\n')
os.symlink('target_dir', dir_sym_root / 'link')
dir_sym_ws = sandbox.Workspace(dir_sym_root, ['*'], [r'^python3\b'])
dir_sym_job, dir_sym_folder = store.new_job('delegate')
dir_sym_task = agent.Task(dir_sym_job, dir_sym_folder, 'goal', dir_sym_ws, [], 5, 0, '', '')
dir_sym_task.take_snapshot()
dir_sym_task.call('run', {'command': 'python3 -c "import os; os.unlink(\'link\'); os.mkdir(\'link\'); open(\'link/a.txt\', \'w\').write(\'from_task\\n\')"'})
dir_sym_task._record_post_state()
dir_sym_task._save('unverified', 'done', [])
# User adds link/importante.txt after task ended
(dir_sym_root / 'link' / 'importante.txt').write_text('keep me!\n')
rb_dir_sym = agent.rollback(dir_sym_job)
ok((dir_sym_root / 'link').is_dir() and not (dir_sym_root / 'link').is_symlink()
   and (dir_sym_root / 'link' / 'importante.txt').read_text() == 'keep me!\n'
   and 'skipped (modified after job ended): link' in rb_dir_sym,
   'rollback() skips replacement directory modified after task ends and preserves link/importante.txt')

# 13. new symlink created by task via run() -> rollback() unlinks the new symlink
new_sym_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(new_sym_root / 'real.txt').write_text('hello\n')
new_sym_ws = sandbox.Workspace(new_sym_root, ['*'], [r'^ln\b'])
new_sym_job, new_sym_folder = store.new_job('delegate')
new_sym_task = agent.Task(new_sym_job, new_sym_folder, 'goal', new_sym_ws, [], 5, 0, '', '')
new_sym_task.call('run', {'command': 'ln -s real.txt fresh_link.txt'})
new_sym_task._record_post_state()
new_sym_task._save('unverified', 'done', [])
ok((new_sym_root / 'fresh_link.txt').is_symlink(), 'new symlink created by run()')
rb_new_sym = agent.rollback(new_sym_job)
ok(not (new_sym_root / 'fresh_link.txt').exists() and not (new_sym_root / 'fresh_link.txt').is_symlink()
   and 'fresh_link.txt' in rb_new_sym and (new_sym_root / 'real.txt').read_text() == 'hello\n',
   'rollback() unlinks newly created symlink without touching target')

# 14. orphaned running job (simulating SIGKILL with missing post_state.json) -> rollback() cautiously skips modified files
sigkill_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(sigkill_root / 'app.py').write_text('v1\n')
sigkill_ws = sandbox.Workspace(sigkill_root, ['*'], [r'^python3\b'])
sigkill_job, sigkill_folder = store.new_job('delegate')
sigkill_task = agent.Task(sigkill_job, sigkill_folder, 'goal', sigkill_ws, [], 5, 0, '', '')
sigkill_task.call('write_file', {'path': 'app.py', 'content': 'v2_from_task\n'})
sigkill_task.call('write_file', {'path': 'new_after_kill.py', 'content': 'user_created\n'})
sigkill_task._save('running', '', [])
# Simulate user edit after SIGKILL (no post_state.json exists, state is still 'running')
(sigkill_root / 'app.py').write_text('v3_user_edit\n')
rb_sigkill = agent.rollback(sigkill_job)
ok('skipped (no post-crash state recorded):' in rb_sigkill
   and 'app.py' in rb_sigkill and 'new_after_kill.py' in rb_sigkill
   and (sigkill_root / 'app.py').read_text() == 'v3_user_edit\n'
   and (sigkill_root / 'new_after_kill.py').read_text() == 'user_created\n',
   'rollback() cautiously skips modified/new files on orphaned running job without post_state.json')

# 15. permission change (chmod +x / 0o755) via run() -> detected in stamp()/changes()/diff() and restored to 0o644 by rollback()
chmod_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
script_p = chmod_root / 'run.sh'
script_p.write_text('#!/bin/sh\necho hi\n')
os.chmod(script_p, 0o644)
stamp_before = sandbox.stamp(chmod_root)
chmod_ws = sandbox.Workspace(chmod_root, ['*'], [r'^chmod\b'])
chmod_job, chmod_folder = store.new_job('delegate')
chmod_task = agent.Task(chmod_job, chmod_folder, 'goal', chmod_ws, [], 5, 0, '', '')
chmod_task.call('run', {'command': 'chmod 755 run.sh'})
stamp_after = sandbox.stamp(chmod_root)
ok(stamp_before['run.sh'] != stamp_after['run.sh'] and stamp_after['run.sh'][2] == 0o755,
   'stamp() detects st_mode change')
ok(('run.sh', 'changed', 0, 0) in chmod_task.changes() and 'mode 0o644 -> 0o755' in chmod_task.diff(),
   'changes() and diff() report mode-only change')
chmod_task._record_post_state()
chmod_task._save('unverified', 'done', [])
rb_chmod = agent.rollback(chmod_job)
ok('run.sh' in rb_chmod and (script_p.stat().st_mode & 0o777) == 0o644,
   'rollback() restores original file permissions (0o644)')

# 16. full directory guard: new conftest.py, rename, chmod, symlink replacement, binary file, SKIP_DIRS, claims
gdir_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
(gdir_root / 'tests' / '__pycache__').mkdir(parents=True)
(gdir_root / 'tests' / '__pycache__' / 'cached.pyc').write_bytes(b'\x00pyc')
(gdir_root / 'tests' / 'test_a.py').write_text('def test_a():\n    assert False\n')
os.chmod(gdir_root / 'tests' / 'test_a.py', 0o644)
(gdir_root / 'tests' / 'fixture.bin').write_bytes(b'\x00\x01\xff\xfe')
(gdir_root / 'tests' / 'other_task.py').write_text('# owned by other\n')
gdir_ws = sandbox.Workspace(gdir_root, write_globs=[], allow_run=[r'^python3\b'])
gdir_ws.name = 'task_a'
gdir_ws.claims = {'tests/other_task.py': 'task_b'}
gdir_ws.protect(['pytest -q'])
gdir_job, gdir_folder = store.new_job('delegate')
gdir_task = agent.Task(gdir_job, gdir_folder, 'goal', gdir_ws, ['pytest -q'], 5, 0, '', '')
gdir_task.take_guard()
# Simulate tampering: new conftest.py, rename, chmod, symlink replacement, binary corruption, new dir+symlink
(gdir_root / 'tests' / 'conftest.py').write_text('def pytest_collection_modifyitems(items): items.clear()\n')
(gdir_root / 'tests' / 'test_renamed.py').write_text('renamed\n')
os.chmod(gdir_root / 'tests' / 'test_a.py', 0o444)
(gdir_root / 'tests' / 'fixture.bin').unlink()
os.symlink('/etc/passwd', gdir_root / 'tests' / 'fixture.bin')
(gdir_root / 'tests' / 'sub').mkdir()
os.symlink('/etc/hosts', gdir_root / 'tests' / 'sub' / 'evil_link')
(gdir_root / 'tests' / 'other_task.py').write_text('# other task legitimate edit\n')
bent_dir = gdir_task.restore_guard()
ok('tests/conftest.py' in bent_dir and not (gdir_root / 'tests' / 'conftest.py').exists(),
   'restore_guard() detects and removes newly created tests/conftest.py')
ok('tests/test_renamed.py' in bent_dir and not (gdir_root / 'tests' / 'test_renamed.py').exists(),
   'restore_guard() removes renamed/extra file inside protected tests/')
ok('tests/test_a.py' in bent_dir and (gdir_root / 'tests' / 'test_a.py').stat().st_mode & 0o777 == 0o644,
   'restore_guard() detects and restores permissions on protected test file')
ok('tests/fixture.bin' in bent_dir and not (gdir_root / 'tests' / 'fixture.bin').is_symlink()
   and (gdir_root / 'tests' / 'fixture.bin').read_bytes() == b'\x00\x01\xff\xfe',
   'restore_guard() replaces symlink with original binary fixture byte-for-byte')
ok('tests/sub/evil_link' in bent_dir and not (gdir_root / 'tests' / 'sub').exists(),
   'restore_guard() removes unauthorized symlink and empty new subdir inside protected tests/')
ok((gdir_root / 'tests' / '__pycache__' / 'cached.pyc').exists(),
   'restore_guard() ignores SKIP_DIRS (__pycache__) inside protected tests/')
ok((gdir_root / 'tests' / 'other_task.py').read_text() == '# other task legitimate edit\n',
   'restore_guard() does not clobber file claimed by another parallel task')

# 17. P2 permission integrity: 0644 -> 0755 -> 0700 (user edit after task) must NOT be overwritten by rollback
pm_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
pm_p = pm_root / 'run.sh'
pm_p.write_text('#!/bin/sh\necho hi\n')
os.chmod(pm_p, 0o644)
pm_ws = sandbox.Workspace(pm_root, ['*'], [r'^chmod\b'])
pm_job, pm_folder = store.new_job('delegate')
pm_task = agent.Task(pm_job, pm_folder, 'goal', pm_ws, [], 5, 0, '', '')
pm_task.call('run', {'command': 'chmod 755 run.sh'})
pm_task._record_post_state()
pm_task._save('unverified', 'done', [])
os.chmod(pm_p, 0o700)
rb_pm = agent.rollback(pm_job)
ok('skipped (modified after job ended): run.sh' in rb_pm and (pm_p.stat().st_mode & 0o777) == 0o700,
   'rollback() preserves post-task user permission change (0644 -> 0755 -> 0700)')

# 17b. legacy post_state.json (bare sha256 without mode) remains compatible
leg_root = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
leg_p = leg_root / 'note.txt'
leg_p.write_text('v1\n')
leg_ws = sandbox.Workspace(leg_root, ['*'])
leg_job, leg_folder = store.new_job('delegate')
leg_task = agent.Task(leg_job, leg_folder, 'goal', leg_ws, [], 5, 0, '', '')
leg_task.call('write_file', {'path': 'note.txt', 'content': 'v2\n'})
leg_task._save('unverified', 'done', [])
import hashlib as _hashlib
store.write_json(leg_folder / 'post_state.json', {
    'note.txt': _hashlib.sha256(b'v2\n').hexdigest(),
})
rb_leg = agent.rollback(leg_job)
ok('restored: note.txt' in rb_leg and leg_p.read_text() == 'v1\n',
   'rollback() remains compatible with legacy post_state.json bare sha256')

# 18. HTML <script> syntax check and orchestrator quality-gate receipt cues
import shutil as _shutil
from tandem_mcp import server as _server
html_dir = Path(tempfile.mkdtemp(dir=Path.home() if os.environ.get('TANDEM_TEST_IN_HOME') else None))
good_html = html_dir / 'good.html'
bad_html = html_dir / 'bad.html'
good_html.write_text('<html><body><script>const x = 1 + 2;</script></body></html>')
bad_html.write_text('<html><body><script>function broken( {</script></body></html>')
if _shutil.which('node'):
    ok(agent.syntax_of(good_html) == '', 'syntax_of() accepts valid inline <script> in HTML')
    ok(bool(agent.syntax_of(bad_html)), 'syntax_of() catches JS syntax error in HTML <script>')

qjob, _ = store.new_job('delegate')
store.write_job(qjob, {
    'kind': 'delegate', 'state': 'verified', 'steps': 2, 'repairs': 0, 'seconds': 1.0, 'tokens': 100,
    'protocol': 'native tool calls', 'summary': 'ok', 'weak': False,
    'changes': [['app.js', 'changed', 35, 10]],
    'before': [{'command': 'test', 'exit': 1}], 'checks': [{'command': 'test', 'exit': 0, 'tail': ''}],
})
ok('Inspect job_diff' in _server._receipt(qjob), '_receipt() surfaces quality-gate reminder on non-trivial verified diff')

sjob, _ = store.new_job('delegate')
store.write_job(sjob, {
    'kind': 'delegate', 'state': 'stuck', 'steps': 4, 'repairs': 0, 'seconds': 10.0, 'tokens': 500,
    'protocol': 'native tool calls', 'summary': 'stuck', 'changes': [], 'before': [], 'checks': [],
})
ok('delegate_many' in _server._receipt(sjob), '_receipt() suggests delegate_many when stuck with no changes')

# hardening after the review ---------------------------------------------------------------------
import socket as _socket  # noqa: E402
import shutil as _shutil  # noqa: E402

# comments and $'..' quoting cannot carry text past the allow list
ok(sandbox.split_command('cat x #pytest')[0] == ['cat x'], 'a shell comment is not part of the command')
ok(sandbox.split_command('pytest -k a#b tests')[0] == ['pytest -k a#b tests'], '# inside a word is not a comment')
ok(sandbox.split_command('make # note\nmake test')[0] == ['make', 'make test'], 'a comment ends at the line end')
cws = sandbox.Workspace(root, [], [r'pytest'])
ok(refused(cws.check_command, 'cat /etc/hostname #pytest'), 'allow list is not satisfied by a comment')
ok(refused(sandbox.split_command, "pytest $'\\''; id #'"), "$'..' quoting is refused")

# host sockets are hidden from the sandbox
run_dir = Path(tempfile.mkdtemp())
(run_dir / 'user' / '1000').mkdir(parents=True)
(run_dir / 'svc').mkdir()
for sock_path in (run_dir / 'docker.sock', run_dir / 'svc' / 'bus.sock'):
    sock = _socket.socket(_socket.AF_UNIX)
    sock.bind(str(sock_path))
    sock.close()
(run_dir / 'plain.txt').write_text('x')
masks = sandbox._socket_masks(str(run_dir))
ok(masks[:2] == ['--tmpfs', str(run_dir / 'user')] and str(run_dir / 'docker.sock') in masks
   and str(run_dir / 'svc' / 'bus.sock') in masks and str(run_dir / 'plain.txt') not in masks,
   '_socket_masks() hides runtime folders and sockets only')
ok('--unshare-ipc' in sandbox.jail_command('true', root), 'jail has its own IPC namespace')
if sandbox.jail_available() and Path('/run/user').is_dir():
    code, out = sandbox.run('ls -A /run/user | wc -l', root, timeout=30, jail=True)
    ok(code == 0 and out.strip() == '0', 'the runtime folder of the user is empty inside the jail')

# secrets in the environment
ok(all(sandbox.SECRET_ENV.search(k) for k in ('PGPASSWORD', 'DATABASE_URL', 'MYSQL_PWD', 'GH_TOKEN', 'REDIS_URL'))
   and not any(sandbox.SECRET_ENV.search(k) for k in ('PWD', 'OLDPWD', 'PATH', 'HOME', 'BASE_URL')),
   'SECRET_ENV covers database URLs and passwords, leaves PWD alone')

# replace_in_file keeps Windows line ends and refuses what is not text
eol_root = Path(tempfile.mkdtemp())
(eol_root / 'a.txt').write_bytes(b'one\r\ntwo\r\nthree\r\n')
(eol_root / 'bad.txt').write_bytes(b'caf\xe9 two\n')
eol_job, eol_folder = store.new_job('delegate')
eol_task = agent.Task(eol_job, eol_folder, 'g', sandbox.Workspace(eol_root), [])
ok(eol_task.call('replace_in_file', {'path': 'a.txt', 'old': 'one\ntwo', 'new': 'one\nTWO'}) == 'replaced'
   and (eol_root / 'a.txt').read_bytes() == b'one\r\nTWO\r\nthree\r\n', 'replace_in_file keeps CRLF line ends')
ok(eol_task.call('replace_in_file', {'path': 'bad.txt', 'old': 'two', 'new': 'TWO'}).startswith('ERROR')
   and (eol_root / 'bad.txt').read_bytes() == b'caf\xe9 two\n', 'replace_in_file leaves a non UTF-8 file alone')

# what a check writes among its own files is not blamed on the executor
art_root = Path(tempfile.mkdtemp())
(art_root / 'tests').mkdir()
(art_root / 'tests' / 'test_a.py').write_text('assert True\n')
art_job, art_folder = store.new_job('delegate')
art_ws = sandbox.Workspace(art_root)
art_task = agent.Task(art_job, art_folder, 'g', art_ws, ['true pytest; touch tests/artifact.out'], unjailed_checks=True)
art_ws.protect(art_task.verify)
art_task.take_guard()
art_checks = art_task.run_checks()
ok(art_checks[0]['exit'] == 0 and not (art_root / 'tests' / 'artifact.out').exists()
   and art_task.restore_guard() == [] and art_task.restored == [], 'artifacts of the checks are removed quietly')
(art_root / 'tests' / 'conftest.py').write_text('x = 1\n')
ok(art_task.restore_guard() == ['tests/conftest.py'] and art_task.restored == ['tests/conftest.py'],
   'a file the executor adds to tests/ is still reported')

# generated folders created by a command
gen_root = Path(tempfile.mkdtemp())
(gen_root / 'tests').mkdir()
(gen_root / 'src').mkdir()
(gen_root / 'tests' / 'test_a.py').write_text('assert True\n')
gen_job, gen_folder = store.new_job('delegate')
gen_ws = sandbox.Workspace(gen_root, ['src/*.py'], [r'^(mkdir|cp)\b'])
gen_task = agent.Task(gen_job, gen_folder, 'g', gen_ws, ['true pytest'])
gen_ws.protect(gen_task.verify)
gen_task.take_guard()
gen_out = gen_task.call('run', {'command': 'mkdir -p tests/build build && cp tests/test_a.py tests/build/conftest.py && cp tests/test_a.py build/any.py'})
ok('removed' in gen_out and not (gen_root / 'tests' / 'build').exists() and not (gen_root / 'build').exists(),
   'generated folders outside the write globs or inside tests/ are removed')
free_root = Path(tempfile.mkdtemp())
(free_root / 'a.py').write_text('x = 1\n')
free_job, free_folder = store.new_job('delegate')
free_task = agent.Task(free_job, free_folder, 'g', sandbox.Workspace(free_root, [], [r'^(mkdir|cp)\b']), [])
free_task.call('run', {'command': 'mkdir dist && cp a.py dist/a.py'})
free_task._save('unverified', 'done', [])
free_task._record_post_state()
ok(free_task.created_dirs == ['dist'] and 'dist' in _server._receipt(free_job), 'a generated folder is recorded and shown in the receipt')
ok('dist/' in agent.rollback(free_job) and not (free_root / 'dist').exists(), 'rollback removes the generated folder')

# syntax checks do not take data for code
syn = Path(tempfile.mkdtemp())
(syn / 'tsconfig.json').write_text('{\n  // strict mode\n  "compilerOptions": {"strict": true, "paths": {"a": ["//x"]},},\n}\n')
(syn / 'package.json').write_text('{"name": "x",}\n')
ok(agent.syntax_of(syn / 'tsconfig.json') == '', 'tsconfig.json may hold comments and trailing commas')
ok(bool(agent.syntax_of(syn / 'package.json')), 'package.json may not')
if _shutil.which('node'):
    (syn / 'data.html').write_text('<script type="application/ld+json">{"a": 1}</script>'
                                   '<script type="x-shader/x-fragment">precision mediump float;</script><script>let a = 1;</script>'
                                   '<script type="module">import {b} from "./b.js"; export const c = b;</script>')
    (syn / 'only.html').write_text('<script type="application/json">{"a": 1}</script>')
    (syn / 'badmod.html').write_text('<script type="module">import {b from "./b.js";</script>')
    ok(agent.syntax_of(syn / 'data.html') == '' and agent.syntax_of(syn / 'only.html') is None
       and bool(agent.syntax_of(syn / 'badmod.html')), 'only JavaScript <script> blocks are checked, modules as modules')

# a server that does not answer is not a server that refuses the schema
class _Refusal(Exception):
    status_code = 400


def _wrapped(cause, text='call failed'):
    try:
        raise engine.ExecutorError(text) from cause
    except engine.ExecutorError as exc:
        return exc


ok(engine._schema_refused(_wrapped(_Refusal())) and engine._schema_refused(_wrapped(None, 'response_format is not supported'))
   and not engine._schema_refused(_wrapped(TimeoutError(), 'Request timed out.')), 'only a refusal turns the forced schema off')

# the API key goes to the configured server only
_old_url = os.environ.get('TANDEM_BASE_URL')
os.environ['TANDEM_BASE_URL'] = 'http://127.0.0.1:1234/v1'
ok(engine._trusted('http://127.0.0.1:1234/v1/models') and engine._trusted('http://127.0.0.1:1234/api/v0/models')
   and not engine._trusted('http://127.0.0.1:8080/v1/models') and not engine._trusted('http://127.0.0.1:12345/v1/models'),
   'only the configured server gets the API key')
if _old_url is None:
    del os.environ['TANDEM_BASE_URL']
else:
    os.environ['TANDEM_BASE_URL'] = _old_url

# reading limits are said, not silent
big = syn / 'big.log'
big.write_text('line\n' * 30)
ok('only the first 100' in sandbox.cut_note(big, 100) and sandbox.cut_note(big) == '', 'cut_note() reports a file read in part')
_old_parts = digest.MAX_PARTS
digest.MAX_PARTS = 2
try:
    digest.answer('word\n' * 40000, 'q', model='none', cache=False)
    too_large = False
except engine.ExecutorError as exc:
    too_large = 'narrow it with grep' in str(exc)
digest.MAX_PARTS = _old_parts
ok(too_large, 'a material of too many parts is refused before any executor call')

# acceptance gates
ujob, ufolder = store.new_job('delegate')
store.write_job(ujob, {'id': ujob, 'kind': 'delegate', 'state': 'unverified', 'workspace': str(root),
                       'changes': [['a.py', 'changed', 1, 1], ['b.py', 'new', 2, 0]], 'checks': [], 'before': []})
(ufolder / 'changes.diff').write_text('--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n--- /dev/null\n+++ b/b.py\n@@ -0,0 +1,2 @@\n+p\n+q')
ok('inspection required' in _server.job_feedback(ujob, True), 'a job without checks needs its diff read before acceptance')
_server.job_diff(ujob, path='nothing.py')
_server.job_diff(ujob, path='a.py')
ok('inspection required' in _server.job_feedback(ujob, True), 'the diff of one file out of two does not open the gate')
_server.job_diff(ujob, path='b.py')
ok(_server.job_feedback(ujob, True) == 'recorded', 'a job without checks is accepted once every changed file was read')

# jobs waiting for a verdict are not kept for ever
old_job, old_folder = store.new_job('delegate')
store.write_job(old_job, {'state': 'unverified', 'accepted': None, 'changes': [['a.py', 'changed', 1, 0]], 'touched': []})
os.utime(old_folder, (0, 0))
store.cleanup(cache_keep=200, jobs_ttl_days=1, jobs_keep=500, preserve_pending=True)
ok(not old_folder.exists(), 'a pending job older than TANDEM_JOBS_PENDING_TTL_DAYS is removed')

# safety list by command name, system folders, ledger, accounting ---------------------------------
dws = sandbox.Workspace(root, [], [r'.'])
for allowed_cmd in ('grep -rn source src', 'cat docs/ssh.md', 'python -m pytest tests/test_exec.py -k kill', 'make nc-test'):
    ok(not refused(dws.check_command, allowed_cmd), f'a denied name as an argument is a plain word: {allowed_cmd}')
for denied_cmd in ('ssh host', '/usr/bin/ssh host', 'FOO=1 ssh host', 'env ssh host', 'xargs kill', 'sh -c "exec id"', '. ./env.sh',
                   'find . -exec chown x {} +', 'source env.sh', 'su root'):
    ok(refused(dws.check_command, denied_cmd), f'safety list: {denied_cmd}')

for system_path in ('/etc', '/usr', '/home', '/tmp', '/usr/bin', '/proc/self'):
    if Path(system_path).is_dir():
        ok(refused(sandbox.Workspace, system_path), f'{system_path} is not a workspace')
fake_home = Path(tempfile.mkdtemp())
(fake_home / '.ssh' / 'keys').mkdir(parents=True)
(fake_home / 'proj').mkdir()
_real_home = os.environ.get('HOME')
os.environ['HOME'] = str(fake_home)
try:
    ok(refused(sandbox.Workspace, fake_home / '.ssh') and refused(sandbox.Workspace, fake_home / '.ssh' / 'keys')
       and refused(sandbox.Workspace, fake_home.parent) and sandbox.Workspace(fake_home / 'proj').root == (fake_home / 'proj').resolve(),
       'credentials folders and the folders above the home are not workspaces, a project in the home is')
    ok(['--tmpfs', str(fake_home / '.ssh')] == sandbox.jail_command('true', fake_home / 'proj')[10 + len(sandbox._socket_masks()):][:2],
       'the jail hides the credentials folder')
finally:
    os.environ['HOME'] = _real_home

store.LEDGER.write_text(json.dumps({'ts': 1.0, 'tool': 'old'}) + '\nnot json\n' + json.dumps({'ts': __import__('time').time(), 'tool': 'new'}) + '\n')
ok(store._trim_ledger(30) == 2 and [r['tool'] for r in store.ledger(10000)] == ['new'] and store._trim_ledger(30) == 0
   and 'ledger_removed' in store.cleanup(), 'old ledger lines are dropped, recent ones kept')

sup_ctx = digest.check_claim_support('debug is enabled', [{'line': 2, 'quote': 'debug = True'}],
                                     ['verbose = False', 'debug = True', '# not used'])
ok(sup_ctx['claim_supported'] == 'quote_only', 'a negation next to the quoted line is not a polarity mismatch')

rd_job, rd_folder = store.new_job('delegate')
rd_task = agent.Task(rd_job, rd_folder, 'g', sandbox.Workspace(root), [])
rd_task.call('read_file', {'path': 'src/a.txt'})
once = rd_task.read_chars
rd_task.call('read_file', {'path': 'src/a.txt'})
rd_task.call('read_file', {'path': 'src/a.txt', 'start': 1, 'end': 1})
ok(once > 0 and rd_task.read_chars == once, 'a file read again is counted once')

_models = engine.models
_connect = engine.connect
engine.connect = lambda *a, **k: {'kind': 'lmstudio', 'url': 'http://x/v1'}
engine.models = lambda refresh=False: [{'id': 'cold', 'loaded': False, 'type': 'llm', 'context': 262144},
                                       {'id': 'warm', 'loaded': True, 'type': 'llm', 'context': 65536},
                                       {'id': 'plain', 'loaded': None, 'type': 'llm', 'context': 32768}]
_ctx_env = os.environ.pop('TANDEM_CONTEXT', None)
try:
    ok(engine.context_tokens('cold') == 8192 and engine.context_tokens('warm') == 65536 and engine.context_tokens('plain') == 32768,
       'the context of a model that is not loaded is not taken from its maximum')
finally:
    engine.models, engine.connect = _models, _connect
    if _ctx_env is not None:
        os.environ['TANDEM_CONTEXT'] = _ctx_env

import tomllib as _tomllib  # noqa: E402
import tandem_mcp as _pkg  # noqa: E402
_project = _tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text())
ok('version' in _project['project']['dynamic'] and _project['tool']['setuptools']['dynamic']['version']['attr'] == 'tandem_mcp.__version__'
   and _pkg.__version__.count('.') == 2, 'the version lives in one place')

# the strict contract --------------------------------------------------------------------------------
os.environ['TANDEM_STRICT'] = '1'
GOAL = 'Fix clamp() in math_utils.py so that values below low return low instead of high.'


def contract_error(goal=GOAL, constraints=None, verify=('python3 -m unittest test_math_utils.py',), globs=('math_utils.py',)):
    try:
        _server._validate_contract(goal, constraints, list(verify), list(globs))
    except ValueError as exc:
        return str(exc)
    return ''


ok(contract_error() == '', 'a contract with a precise goal, named files and a real check is accepted')
ok('write_globs is required' in contract_error(globs=()), 'strict: no write_globs, no task')
ok(all('matches every file' in contract_error(globs=(g,)) for g in ('*', '**', '**/*', './*', '*.*')), 'strict: catch-all write_globs are refused')
ok(contract_error(globs=('src/**',)) == '' and contract_error(globs=('*.py',)) == '', 'strict: a folder or a file type is a named target')
ok('verify_commands is required' in contract_error(verify=()), 'strict: no check, no task')
ok(all('cannot fail' in contract_error(verify=(v,)) for v in ('true', 'echo done', ': ; exit 0')), 'strict: a check that cannot fail is refused')
ok('goal must name its targets' in contract_error(goal='Make the page look nicer and more modern please ok'), 'strict: a goal without targets is refused')
ok('constraints are required' in contract_error(verify=('grep -q clamp math_utils.py', 'test -f math_utils.py')),
   'strict: checks that only look for text need constraints')
ok('constraints are required' in contract_error(verify=('for f in a.py b.py; do grep -q x "$f" || exit 1; done',)),
   'strict: a loop of greps is still a presence check')
ok(contract_error(verify=('grep -q clamp math_utils.py',), constraints=['clamp(-3, 0, 10) returns 0 in math_utils.py']) == '',
   'strict: presence checks with constraints are accepted')
ok(contract_error(verify=('grep -q clamp math_utils.py', 'node --check app.js')) == '', 'strict: a check that runs a tool is not a presence check')
ok('write_globs is required' in _server.delegate(GOAL, str(root), verify_commands=['python3 -m unittest test_math_utils.py'])
   and 'verify_commands is required' in _server.delegate_many([{'name': 'a', 'goal': GOAL, 'write_globs': ['math_utils.py']}], str(root)),
   'strict: delegate and delegate_many refuse before the executor is called')
sjob2, sfolder2 = store.new_job('delegate')
store.write_job(sjob2, {'id': sjob2, 'kind': 'delegate', 'state': 'verified', 'workspace': str(root),
                        'changes': [['a.py', 'changed', 1, 1]], 'checks': [], 'before': []})
(sfolder2 / 'changes.diff').write_text('--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y')
ok('inspection required' in _server.job_feedback(sjob2, True) and bool(_server.job_diff(sjob2)) and _server.job_feedback(sjob2, True) == 'recorded',
   'strict: even a small verified change is accepted only after its diff was read')
ok('look no command can prove' in contract_error(goal='Create index.html with a full-viewport canvas id="c" and a HUD panel.',
                                                    verify=('node check_page.js',), globs=('index.html',))
   and contract_error(goal='Create index.html with a full-viewport canvas id="c" and a HUD panel.', verify=('node check_page.js',),
                      globs=('index.html',), constraints=['the .hud panel is fixed at top: 14px']) == '',
   'strict: a task that writes visual files needs the design written as constraints')
vjob, vfolder = store.new_job('delegate')
store.write_job(vjob, {'id': vjob, 'kind': 'delegate', 'state': 'verified', 'workspace': str(root), 'constraints': ['the .hud panel is fixed'],
                       'changes': [['index.html', 'new', 10, 0]], 'checks': [], 'before': []})
ok('render the result and compare it with each constraint' in _server._receipt(vjob), 'the receipt of a visual job asks for a render check')
ok(all('one requirement per constraint' in contract_error(constraints=[c]) for c in (
        'clamp(-3, 0, 10) returns 0 in math_utils.py; clamp(15, 0, 10) returns 10',
        'clamp(-3, 0, 10) returns 0 in math_utils.py. Values above high return high',
        'clamp in math_utils.py ' + 'returns low for values below low and ' * 5))
   and contract_error(constraints=['clamp(-3, 0, 10) returns 0 in math_utils.py', 'clamp(15, 0, 10) returns 10.5 at most']) == '',
   'strict: a constraint holds one requirement')
os.environ['TANDEM_STRICT'] = '0'
ok(_server.strict() is False and contract_error(globs=(), verify=()) == '', 'TANDEM_STRICT=0 brings the loose contract back')

# --- P0/P1 hardening checks ---
code_cap, out_cap = sandbox.run('python3 -c "print(\'A\' * 20000)"', root, max_output_bytes=4096)
ok(code_cap == 0 and '[output truncated:' in out_cap and len(out_cap) < 5000, 'sandbox.run caps output in RAM')

code_ht, out_ht = sandbox.run('python3 -c "print(\'H\'*5000); print(\'M\'*5000); print(\'TAILMARKER\')"',
                              root, max_output_bytes=4096)
ok(code_ht == 0 and 'TAILMARKER' in out_ht and '[output truncated:' in out_ht and 'H' in out_ht,
   'sandbox.run keeps head+tail when truncating output')

t_hang = time.time()
code_hang, _ = sandbox.run('python3 -c "import os,time; pid=os.fork(); (os.setsid(), time.sleep(5)) if pid==0 else time.sleep(5)"',
                           root, timeout=1)
ok(code_hang == 124 and (time.time() - t_hang) < 8.0, 'sandbox.run does not hang on detached child keeping stdout open')

ok({'.claude', '.codex', '.gemini'}.issubset(set(sandbox.SECRETS)), 'SECRETS hides client config directories')
redacted = sandbox.redact_secrets(
    'OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnop\n'
    'Authorization: Bearer my_super_secret_bearer_token_12345\n'
    '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n'
)
ok('sk-proj-' not in redacted and 'my_super_secret_bearer_token_12345' not in redacted
   and 'MIIEowIBAAKCAQEA' not in redacted and '[REDACTED_PRIVATE_KEY]' in redacted,
   'redact_secrets masks keys, tokens and PEM blocks')

saved_red = _server._saved('digest_file', 100, 'OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnop')
fail_red = _server._fail('Bearer abcdef1234567890abcdef')
benign_red = sandbox.redact_secrets('MONKEY_COUNT=5\nKEYBOARD_LAYOUT=us\n')
ok('[REDACTED' in saved_red and 'sk-proj-' not in saved_red
   and '[REDACTED_TOKEN]' in fail_red and 'abcdef1234567890abcdef' not in fail_red
   and 'MONKEY_COUNT=5' in benign_red and 'KEYBOARD_LAYOUT=us' in benign_red
   and '.m2/settings.xml' in sandbox.SECRETS and '.m2' not in sandbox.SECRETS
   and '.gradle/gradle.properties' in sandbox.SECRETS,
   'choke-point redaction, SECRET_ENV precision, and narrowed SECRETS')

spoof_file = root / 'spoof.txt'
spoof_file.write_text('aaaa')
st_orig = spoof_file.stat()
s1 = sandbox.stamp(root)
spoof_file.write_text('bbbb')
os.utime(spoof_file, ns=(st_orig.st_atime_ns, st_orig.st_mtime_ns))
s2 = sandbox.stamp(root)
ok(s1['spoof.txt'][1] != s2['spoof.txt'][1], 'stamp ctime_ns fast-path still catches mtime+size spoofing')

nt_root = Path(tempfile.mkdtemp())
(nt_root / 'a.txt').write_text('hello')
old_os_name = sandbox.os.name
try:
    sandbox.os.name = 'nt'
    sandbox.stamp(nt_root)
    ok(os.fspath(nt_root) not in sandbox._STAMP_CACHE, 'stamp does not populate cache on non-POSIX')
finally:
    sandbox.os.name = old_os_name

stale_job, _ = store.new_job('delegate')
stale_data = store.read_job(stale_job)
stale_data['started'] = time.time() - 300
store.write_job(stale_job, stale_data)
live_job, _ = store.new_job('delegate')
live_data = store.read_job(live_job)
live_data['started'] = time.time() - 300
store.write_job(live_job, live_data)
fresh_batch, _ = store.new_job('batch')
old_batch_locked, _ = store.new_job('batch')
obl_data = store.read_job(old_batch_locked)
obl_data['started'] = time.time() - 300
store.write_job(old_batch_locked, obl_data)
old_batch_unlocked, _ = store.new_job('batch')
obu_data = store.read_job(old_batch_unlocked)
obu_data['started'] = time.time() - 300
store.write_job(old_batch_unlocked, obu_data)
lk = store.acquire_job_lock(live_job)
lk_batch = store.acquire_job_lock(old_batch_locked)
try:
    ok(store.is_job_locked(live_job) and not store.is_job_locked(stale_job), 'job flock reports live vs stale lock')
    fixed_n = store.reconcile_stale_jobs()
    ok(fixed_n >= 2
       and store.read_job(stale_job)['state'] == 'error'
       and store.read_job(live_job)['state'] == 'running'
       and store.read_job(fresh_batch)['state'] == 'running'
       and store.read_job(old_batch_locked)['state'] == 'running'
       and store.read_job(old_batch_unlocked)['state'] == 'error',
       'reconcile_stale_jobs respects grace period and locks for jobs and batches')
finally:
    store.release_job_lock(lk)
    store.release_job_lock(lk_batch)

ok('no job' in _server.job_stop('nonexistent-job-id'), 'job_stop handles unknown job id')

# --- P0 #6: transient error classification and retry in engine.chat ---
class _DummyHTTP(Exception):
    def __init__(self, status_code, msg='err'):
        super().__init__(msg)
        self.status_code = status_code


ok(all(engine._transient(_DummyHTTP(c)) for c in (502, 429, 503))
   and not any(engine._transient(_DummyHTTP(c)) for c in (400, 401, 404))
   and engine._transient(ConnectionError('reset')),
   '_transient classifies HTTP status codes and connection errors')
try:
    raise engine.ExecutorError('wrapped') from _DummyHTTP(502)
except engine.ExecutorError as wrapped_err:
    ok(engine.transient_error(wrapped_err), 'transient_error inspects __cause__')

old_create = engine._create
old_connect = engine.connect
old_sleep = time.sleep
old_retries = os.environ.get('TANDEM_LLM_RETRIES')
sleeps = []
call_n = 0
fake_resp = types.SimpleNamespace(
    choices=[types.SimpleNamespace(
        message=types.SimpleNamespace(content='{"ok": true}', tool_calls=None),
        finish_reason='stop',
    )],
    usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
)


def _flaky_create(*_a, **_kw):
    global call_n
    call_n += 1
    if call_n <= 2:
        raise _DummyHTTP(502, 'bad gateway')
    return fake_resp


def _bad_create(*_a, **_kw):
    global call_n
    call_n += 1
    raise _DummyHTTP(400, 'bad request')


try:
    engine.connect = lambda refresh=False: {'name': 'fake', 'url': 'http://127.0.0.1:1/v1', 'kind': 'lmstudio', 'client': None}
    time.sleep = lambda s: sleeps.append(s)
    os.environ['TANDEM_LLM_RETRIES'] = '2'
    engine._create = _flaky_create
    reply, _ = engine.chat([{'role': 'user', 'content': 'hi'}], tool='ask', model='test-m')
    retry_rows = [r for r in store.ledger(1) if r.get('kind') == 'retry' and r.get('model') == 'test-m']
    ok(reply.content == '{"ok": true}' and call_n == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0]
       and len(retry_rows) == 2,
       'engine.chat retries transient errors with increasing backoff and logs retry rows')

    call_n = 0
    engine._create = _bad_create
    got_400 = False
    try:
        engine.chat([{'role': 'user', 'content': 'hi'}], tool='ask', model='test-m')
    except engine.ExecutorError as exc_400:
        got_400 = call_n == 1 and getattr(exc_400.__cause__, 'status_code', None) == 400
    ok(got_400, 'engine.chat fails immediately on 400 and preserves __cause__')

    import httpx
    from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
    req = httpx.Request('POST', 'http://127.0.0.1:1/v1/chat/completions')
    ok(engine._transient(APIConnectionError(request=req)), 'real APIConnectionError is transient')
    ok(not engine._transient(APITimeoutError(request=req)), 'generation timeout is not retried')
    ok(engine._transient(RateLimitError('rl', response=httpx.Response(429, request=req), body=None)), 'real 429 is transient')
    ok(engine._transient(InternalServerError('ise', response=httpx.Response(503, request=req), body=None)), 'real 5xx is transient')
    try:
        raise engine.ExecutorError('wrapped conn') from APIConnectionError(request=req)
    except engine.ExecutorError as wrapped_conn:
        ok(engine.transient_error(wrapped_conn), 'transient_error handles real APIConnectionError __cause__')

    conn_calls = 0

    def _conn_flaky_create(*_a, **_kw):
        global conn_calls
        conn_calls += 1
        if conn_calls <= 2:
            raise APIConnectionError(request=req)
        return fake_resp

    before_retries = len([r for r in store.ledger(1) if r.get('kind') == 'retry' and r.get('model') == 'test-conn'])
    engine._create = _conn_flaky_create
    reply_conn, _ = engine.chat([{'role': 'user', 'content': 'hi'}], tool='ask', model='test-conn')
    after_retries = len([r for r in store.ledger(1) if r.get('kind') == 'retry' and r.get('model') == 'test-conn'])
    ok(reply_conn.content == '{"ok": true}' and conn_calls == 3 and (after_retries - before_retries) == 2,
       'engine.chat retries real APIConnectionError end-to-end')
finally:
    engine._create = old_create
    engine.connect = old_connect
    time.sleep = old_sleep
    if old_retries is None:
        os.environ.pop('TANDEM_LLM_RETRIES', None)
    else:
        os.environ['TANDEM_LLM_RETRIES'] = old_retries

# Auto-resume in Task.loop on transient ExecutorError
ar_job, ar_folder = store.new_job('delegate')
ar_ws = sandbox.Workspace(str(root), ['math_utils.py'])
ar_task = agent.Task(ar_job, ar_folder, 'auto resume test', ar_ws, [], max_steps=5)
ar_calls = 0


def _ar_turn(_msgs):
    global ar_calls
    ar_calls += 1
    if ar_calls == 1:
        try:
            raise _DummyHTTP(502, 'reloading')
        except _DummyHTTP as e:
            raise engine.ExecutorError('transient 502') from e
    return [(None, 'finish', {'summary': 'recovered'})]


ar_task._turn = _ar_turn
old_ar_sleep = time.sleep
old_ar_env = os.environ.get('TANDEM_JOB_AUTORESUME')
try:
    time.sleep = lambda _s: None
    os.environ['TANDEM_JOB_AUTORESUME'] = '2'
    ar_state = ar_task.loop([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}])
    ok(ar_state != 'error' and ar_task.resumes == 1
       and any('auto-resume' in str(entry) for entry in ar_task.log),
       'Task.loop auto-resumes after transient ExecutorError')

    ar_job0, ar_folder0 = store.new_job('delegate')
    ar_task0 = agent.Task(ar_job0, ar_folder0, 'auto resume off', ar_ws, [], max_steps=5)
    ar_calls = 0
    ar_task0._turn = _ar_turn
    os.environ['TANDEM_JOB_AUTORESUME'] = '0'
    t_ar0 = agent._launch(ar_task0, lambda: ar_task0.loop([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]))
    t_ar0.join(timeout=10)
    ok((store.read_job(ar_job0) or {}).get('state') == 'error', 'TANDEM_JOB_AUTORESUME=0 disables auto-resume')
finally:
    time.sleep = old_ar_sleep
    agent.STOP.pop(ar_job0, None)
    agent.RUNNING.pop(ar_job0, None)
    if old_ar_env is None:
        os.environ.pop('TANDEM_JOB_AUTORESUME', None)
    else:
        os.environ['TANDEM_JOB_AUTORESUME'] = old_ar_env

# --- P0 #4a: outbound symlink refusal in unjailed sandbox.run ---
sym_root = Path(tempfile.mkdtemp())
ext_dir = Path(tempfile.mkdtemp())
ext_file = ext_dir / 'outside.txt'
ext_file.write_text('secret\n')
(sym_root / 'inside.txt').write_text('ok\n')
ok(sandbox.outbound_symlinks(sym_root) == [], 'outbound_symlinks is empty on clean tree')

(sym_root / 'in_link').symlink_to(sym_root / 'inside.txt')
code_in, _ = sandbox.run('echo ok', sym_root, jail=False)
ok(code_in == 0 and sandbox.outbound_symlinks(sym_root) == [], 'inbound symlink is allowed')

(sym_root / 'node_modules').mkdir()
(sym_root / 'node_modules' / 'ext_skip').symlink_to(ext_file)
ok(sandbox.outbound_symlinks(sym_root) == [], 'symlinks inside SKIP_DIRS are ignored')

(sym_root / 'out_link').symlink_to(ext_file)
old_allow_sym = os.environ.get('TANDEM_ALLOW_OUTBOUND_SYMLINKS')
try:
    got_sym_err = ''
    try:
        sandbox.run('echo x', sym_root, jail=False)
    except sandbox.SandboxError as exc_sym:
        got_sym_err = str(exc_sym)
    ok('out_link' in got_sym_err, 'unjailed run refuses workspace with outbound symlink')

    code_exempt, _ = sandbox.run('echo x', sym_root, jail=False, guard_symlinks=False)
    ok(code_exempt == 0, 'guard_symlinks=False exempts digest_command')

    os.environ['TANDEM_ALLOW_OUTBOUND_SYMLINKS'] = '1'
    code_optout, _ = sandbox.run('echo x', sym_root, jail=False)
    ok(code_optout == 0, 'TANDEM_ALLOW_OUTBOUND_SYMLINKS=1 allows unjailed run')
finally:
    if old_allow_sym is None:
        os.environ.pop('TANDEM_ALLOW_OUTBOUND_SYMLINKS', None)
    else:
        os.environ['TANDEM_ALLOW_OUTBOUND_SYMLINKS'] = old_allow_sym
    (sym_root / 'out_link').unlink()

(sym_root / 'rel_out').symlink_to('../../etc/passwd')
(sym_root / 'dangling_out').symlink_to(str(ext_dir / 'does_not_exist'))
offenders = sandbox.outbound_symlinks(sym_root)
ok('rel_out' in offenders and 'dangling_out' in offenders, 'relative and dangling outbound symlinks are detected')
for bad_link in ('rel_out', 'dangling_out'):
    got_err = False
    try:
        sandbox.run('echo x', sym_root, jail=False)
    except sandbox.SandboxError:
        got_err = True
    ok(got_err, f'unjailed run refuses {bad_link}')
    (sym_root / bad_link).unlink()

st_sym = sandbox.stamp(sym_root)
ok(st_sym['in_link'][1] == 'symlink:' + str(sym_root / 'inside.txt'), 'stamp still records symlinks as target string')

# --- P0 #4b: configurable snapshot caps and receipt warning ---
cap_root = Path(tempfile.mkdtemp())
(cap_root / 'big.bin').write_bytes(b'X' * 4096)
old_snap_cap = os.environ.get('TANDEM_SNAPSHOT_FILE_CAP')
try:
    os.environ['TANDEM_SNAPSHOT_FILE_CAP'] = '1024'
    cap_job, cap_folder = store.new_job('delegate')
    cap_ws = sandbox.Workspace(str(cap_root), ['big.bin'], allow_run=['^echo'])
    cap_task = agent.Task(cap_job, cap_folder, 'snap cap test', cap_ws, [], max_steps=2)
    cap_task.take_snapshot()
    snap_manifest = store.read_json(cap_folder / 'snapshot.json')
    cap_task.touched.add('big.bin')
    b_status, b_unbacked = cap_task._backup_status()
    cap_task._save('unverified', 'done', [])
    cap_data = store.read_job(cap_job)
    cap_receipt = _server._receipt(cap_job)
    ok(snap_manifest.get('big.bin') is None
       and b_status == 'unbacked' and 'big.bin' in b_unbacked
       and 'big.bin' in (cap_data.get('unbacked_files') or [])
       and 'WARNING:' in cap_receipt and 'TANDEM_SNAPSHOT_FILE_CAP' in cap_receipt,
       'configurable snapshot caps track unbacked files and surface warning in receipt')
finally:
    if old_snap_cap is None:
        os.environ.pop('TANDEM_SNAPSHOT_FILE_CAP', None)
    else:
        os.environ['TANDEM_SNAPSHOT_FILE_CAP'] = old_snap_cap

# Invalid snapshot cap env falls back to default (8 MiB) without raising
try:
    os.environ['TANDEM_SNAPSHOT_FILE_CAP'] = '8MB'
    inv_job, inv_folder = store.new_job('delegate')
    inv_ws = sandbox.Workspace(str(cap_root), ['big.bin'], allow_run=['^echo'])
    inv_task = agent.Task(inv_job, inv_folder, 'invalid cap test', inv_ws, [], max_steps=2)
    inv_task.take_snapshot()
    inv_manifest = store.read_json(inv_folder / 'snapshot.json')
    ok(inv_manifest.get('big.bin') is not None, 'invalid TANDEM_SNAPSHOT_FILE_CAP falls back to default')
finally:
    if old_snap_cap is None:
        os.environ.pop('TANDEM_SNAPSHOT_FILE_CAP', None)
    else:
        os.environ['TANDEM_SNAPSHOT_FILE_CAP'] = old_snap_cap

# Default 8 MiB cap backs up a 3 MB file (above old 2 MB cap)
import shutil
big3_root = Path(tempfile.mkdtemp())
old_total_cap = os.environ.get('TANDEM_SNAPSHOT_TOTAL_CAP')
try:
    (big3_root / 'three_mb.bin').write_bytes(b'Z' * (3 * 1024 * 1024))
    os.environ.pop('TANDEM_SNAPSHOT_FILE_CAP', None)
    os.environ.pop('TANDEM_SNAPSHOT_TOTAL_CAP', None)
    b3_job, b3_folder = store.new_job('delegate')
    b3_ws = sandbox.Workspace(str(big3_root), ['three_mb.bin'], allow_run=['^echo'])
    b3_task = agent.Task(b3_job, b3_folder, '3mb default cap test', b3_ws, [], max_steps=2)
    b3_task.take_snapshot()
    b3_manifest = store.read_json(b3_folder / 'snapshot.json')
    b3_task.touched.add('three_mb.bin')
    b3_status = b3_task._backup_status()
    b3_task._save('unverified', 'done', [])
    b3_data = store.read_job(b3_job)
    b3_receipt = _server._receipt(b3_job)
    ok(b3_manifest.get('three_mb.bin') is not None
       and b3_status == ('fully_backed', [])
       and not (b3_data.get('unbacked_files') or [])
       and 'TANDEM_SNAPSHOT_FILE_CAP' not in b3_receipt,
       'default 8 MiB cap backs up 3 MB file without unbacked warning')
finally:
    shutil.rmtree(big3_root, ignore_errors=True)
    if old_snap_cap is None:
        os.environ.pop('TANDEM_SNAPSHOT_FILE_CAP', None)
    else:
        os.environ['TANDEM_SNAPSHOT_FILE_CAP'] = old_snap_cap
    if old_total_cap is None:
        os.environ.pop('TANDEM_SNAPSHOT_TOTAL_CAP', None)
    else:
        os.environ['TANDEM_SNAPSHOT_TOTAL_CAP'] = old_total_cap

# --- P1 #9: parallel server discovery and cached servers() ---
old_answers = engine._answers
old_kind = engine._kind
old_state = dict(engine._state)
old_srv_cache = dict(engine._servers_cache)
old_tb = os.environ.pop('TANDEM_BASE_URL', None)
old_lm = os.environ.pop('LM_STUDIO_BASE_URL', None)
try:
    engine._state.update(url=None, kind=None, name=None, client=None, models=None, models_at=0.0, pinned='')
    engine._kind = lambda _u: 'openai'

    def _prio_answers(u):
        if '11434' in u:
            time.sleep(0.2)
            return True
        if '8081' in u:
            return True
        return False

    engine._answers = _prio_answers
    st_prio = engine.connect(refresh=True)
    ok(st_prio['url'] == 'http://127.0.0.1:11434/v1' and st_prio['name'] == 'Ollama',
       'parallel connect preserves KNOWN priority order and matching name')

    engine._state.update(url=None, pinned='')

    def _slow_all(_u):
        time.sleep(0.2)
        return True

    engine._answers = _slow_all
    t_par = time.time()
    engine.connect(refresh=True)
    ok(time.time() - t_par < 1.0, 'parallel connect finishes all 8 slow probes in < 1.0 s')

    engine._state.update(url=None, pinned='')
    engine._answers = lambda _u: False
    t_none = time.time()
    got_no_srv = False
    try:
        engine.connect(refresh=True)
    except engine.ExecutorError:
        got_no_srv = True
    ok(got_no_srv and time.time() - t_none < 1.0, 'parallel connect fails fast when no server answers')

    probe_count = 0

    def _count_answers(u):
        global probe_count
        probe_count += 1
        return '1234' in u

    engine._answers = _count_answers
    engine._servers_cache.update(at=0.0, rows=[])
    r1 = engine.servers()
    r2 = engine.servers()
    ok(probe_count == len(engine.KNOWN) and r1 == r2 and len(r1) == 1,
       'servers() caches results within TTL')

    probe_count = 0
    os.environ['TANDEM_BASE_URL'] = 'http://127.0.0.1:9999/v1'
    engine._state.update(url=None, pinned='')
    engine.connect(refresh=True)
    ok(probe_count == 0, 'forced TANDEM_BASE_URL skips _answers discovery')
    os.environ.pop('TANDEM_BASE_URL', None)

    engine._state.update(url=None, pinned='')
    ok(not engine._trusted('http://127.0.0.1:8081/v1/models'), '_trusted remains False for unconfigured port')
finally:
    engine._answers = old_answers
    engine._kind = old_kind
    engine._state.clear()
    engine._state.update(old_state)
    engine._servers_cache.clear()
    engine._servers_cache.update(old_srv_cache)
    if old_tb is not None:
        os.environ['TANDEM_BASE_URL'] = old_tb
    if old_lm is not None:
        os.environ['LM_STUDIO_BASE_URL'] = old_lm

# --- P1 #10A: release finished Task objects from RUNNING and keep job_diff accurate ---
rel_job, rel_folder = store.new_job('delegate')
rel_ws = sandbox.Workspace(str(root), ['math_utils.py'])
rel_task = agent.Task(rel_job, rel_folder, 'release task test', rel_ws, [], max_steps=2)
rel_task._turn = lambda _m: [(None, 'finish', {'summary': 'done'})]
t_rel = agent._launch(rel_task, lambda: rel_task.loop([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]))
t_rel.join(timeout=10)
ok(rel_job in agent.RUNNING and agent.RUNNING[rel_job][0] is t_rel and agent.RUNNING[rel_job][1] is None,
   'finished job drops Task object from RUNNING while keeping thread entry')

(rel_folder / 'changes.diff').write_text('--- a/math_utils.py\n+++ b/math_utils.py\n@@ -1 +1 @@\n-a\n+b\n')
diff_rel = _server.job_diff(rel_job)
ok('this is a batch' not in diff_rel and '+b' in diff_rel,
   'job_diff on finished delegate reads changes.diff instead of mistaking it for a batch')

live_batch, _ = store.new_job('batch')
ev_batch = threading.Event()
th_batch = threading.Thread(target=ev_batch.wait, args=(5,), daemon=True)
th_batch.start()
agent.RUNNING[live_batch] = (th_batch, None)
try:
    ok('this is a batch' in _server.job_diff(live_batch), 'job_diff on live batch reports batch')
finally:
    ev_batch.set()
    th_batch.join(timeout=2)
    agent.RUNNING.pop(live_batch, None)

done_batch, _ = store.new_job('batch')
b_data = store.read_job(done_batch)
b_data['state'] = 'verified'
store.write_job(done_batch, b_data)
ok('this is a batch' in _server.job_diff(done_batch), 'job_diff on finished batch reports batch')

ok(agent.request_stop(rel_job) is False and agent.rollback(rel_job) == 'no journal for this job',
   'finished job rollback/stop work with cleared Task')
agent.RUNNING.pop(rel_job, None)

# request_stop during finishing window (alive thread, STOP already popped) must not leak STOP entry
win_job, win_folder = store.new_job('delegate')
win_ws = sandbox.Workspace(str(root), ['math_utils.py'])
win_task = agent.Task(win_job, win_folder, 'stop window test', win_ws, [], max_steps=2)
win_gate = threading.Event()
try:
    t_win = agent._launch(win_task, lambda: (win_gate.wait(timeout=5), 'verified')[1])
    agent.STOP.pop(win_job, None)
    res_win = agent.request_stop(win_job)
    ok(res_win is True and win_job not in agent.STOP,
       'request_stop during finishing window returns True without creating orphan STOP event')
finally:
    win_gate.set()
    if 't_win' in locals():
        t_win.join(timeout=5)
    agent.STOP.pop(win_job, None)
    agent.RUNNING.pop(win_job, None)
ok(agent.request_stop('finished-job-id') is False and 'finished-job-id' not in agent.STOP,
   'request_stop on dead job returns False without poisoning STOP')
stop_job, stop_folder = store.new_job('delegate')
stop_ws = sandbox.Workspace(str(root), ['math_utils.py'])
stop_task = agent.Task(stop_job, stop_folder, 'stop test', stop_ws, [], max_steps=5)
agent.STOP[stop_job] = threading.Event()
agent.STOP[stop_job].set()
stop_state = stop_task.loop([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}])
agent.STOP.pop(stop_job, None)
ok(stop_state == 'stopped' and store.read_job(stop_job)['state'] == 'stopped', 'STOP event exits Task.loop cleanly as stopped')

# Regression: pre-poisoned STOP event must not stop a fresh _launch
poison_job, poison_folder = store.new_job('delegate')
poison_task = agent.Task(poison_job, poison_folder, 'poison test', stop_ws, [], max_steps=2)
poison_task._turn = lambda msgs: (_ for _ in ()).throw(engine.ExecutorError('no server'))
agent.STOP[poison_job] = threading.Event()
agent.STOP[poison_job].set()
try:
    t_poison = agent._launch(poison_task, lambda: poison_task.loop([{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}]))
    t_poison.join(timeout=10)
    ok((store.read_job(poison_job) or {}).get('state') == 'error', '_launch replaces pre-set STOP event')
finally:
    agent.STOP.pop(poison_job, None)
    agent.RUNNING.pop(poison_job, None)

# Fail-closed lock in _launch
locked_job, locked_folder = store.new_job('delegate')
locked_task = agent.Task(locked_job, locked_folder, 'lock test', stop_ws, [], max_steps=2)
lk_held = store.acquire_job_lock(locked_job)
try:
    got_lock_err = False
    try:
        agent._launch(locked_task, lambda: 'verified')
    except OSError:
        got_lock_err = True
    ok(got_lock_err, '_launch fails closed with OSError when job lock is already held')
finally:
    store.release_job_lock(lk_held)
    agent.STOP.pop(locked_job, None)
    agent.RUNNING.pop(locked_job, None)

print(f'{checks} checks, 0 failures')
