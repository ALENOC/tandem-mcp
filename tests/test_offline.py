"""Checks that need no model: sandbox limits, evidence check, journal and rollback, parsing."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
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
    ok(sandbox.run(probe, root)[1].split()[-1] == '0', 'without the jail the host port is reachable')
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
print(f'{checks} checks, 0 failures')
