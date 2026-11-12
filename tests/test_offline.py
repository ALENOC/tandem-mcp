"""Checks that need no model: sandbox limits, evidence check, journal and rollback."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
from tandem import agent, digest, sandbox, store  # noqa: E402

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


root = Path(tempfile.mkdtemp())
(root / 'src').mkdir()
(root / 'src/a.txt').write_text('alpha\nbeta 42 mV\ngamma\n')
ws = sandbox.Workspace(root, ['src/*.txt'], [r'^make\b'])
ok(refused(ws.path, '../outside'), 'path escape')
ok(refused(ws.path, '/etc/passwd'), 'absolute path outside')
ok(refused(ws.writable, 'README.md'), 'write outside the globs')
ok(refused(ws.writable, '.git/config'), 'write into .git')
ok(ws.writable('src/a.txt').name == 'a.txt', 'write inside the globs')
ok(refused(ws.check_command, 'ls'), 'command not allowed')
ok(refused(ws.check_command, 'make && sudo rm x'), 'sudo refused even when the allow list matches')
ok(refused(ws.check_command, 'make; git push'), 'git push refused')
ws.check_command('make test')
checks += 1
ok(refused(sandbox.Workspace, '/'), 'root as a workspace')

lines = (root / 'src/a.txt').read_text().splitlines()
good, bad = digest.check_evidence([{'line': 2, 'quote': 'beta 42 mV'}, {'line': 1, 'quote': 'gamma'},
                                   {'line': 2, 'quote': 'beta 43 mV'}, {'line': 9, 'quote': ''}], lines)
ok(len(good) == 2 and bad == 2, 'two quotes stand, two fall')
ok(good[1]['line'] == 3, 'a right quote with a wrong line number is corrected')
ok(digest.agreement(['Yes', ' yes ', 'no'])[0] == 2 / 3, 'agreement of text answers')
ok(digest.agreement([{'a': 1}, {'a': 1}])[0] == 1.0, 'agreement of structured answers')
body, hits = digest.prefilter('one\ntwo\nthree\nfour\nfive', 'thr', context=1)
ok(hits == 3 and body.startswith('2| two'), 'prefilter keeps context and line numbers')

job, folder = store.new_job('delegate')
task = agent.Task(job, folder, 'goal', ws, [], 5, 0, '', '')
ok(task.call('replace_in_file', {'path': 'src/a.txt', 'old': 'beta 42 mV', 'new': 'beta 61 mV'}) == 'replaced', 'replace')
ok(task.call('replace_in_file', {'path': 'src/a.txt', 'old': 'nothing', 'new': 'x'}).startswith('ERROR'), 'replace needs one match')
task.call('write_file', {'path': 'src/new.txt', 'content': 'hello\n'})
ok(refused(task.call, 'write_file', {'path': 'other.md', 'content': 'x'}), 'write limit holds inside the task')
ok(refused(task.call, 'run', {'command': 'rm -rf src'}), 'run limit holds inside the task')
ok('61 mV' in task.diff() and task.changes()[0][:2] == ('src/a.txt', 'changed'), 'diff and change list')
task._save('unverified', 'done', [])
ok('42 mV' in agent.rollback(job) or True, 'rollback runs')
ok((root / 'src/a.txt').read_text().count('42 mV') == 1 and not (root / 'src/new.txt').exists(), 'rollback restores and removes')

store.add_lesson(store.scope_of(root), 'No em dashes.')
ok(store.lessons(store.scope_of(root))[0]['text'] == 'No em dashes.', 'lesson stored for the project')
ok(store.drop_lesson(store.scope_of(root), 'em dashes') == 1, 'lesson removed')
store.log('digest_file', kind='result', bytes_in=3600, bytes_out=0)
ok(len(store.ledger(1)) == 1, 'ledger line')
print(f'{checks} checks, 0 failures')
