"""Offline tests for reversible write_file compaction, read_file recovery, resume, and JSON fallback."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_host_runner import SlowFake  # noqa: E402
from tandem_mcp import agent, engine, sandbox, store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_compact_test_'))
store.DATA = tmp / 'data'
store.JOBS = store.DATA / 'jobs'
store.CACHE = store.DATA / 'cache'
store.LEDGER = store.DATA / 'ledger.jsonl'
store.LESSONS = store.DATA / 'lessons.jsonl'
store.MODELS = store.DATA / 'models.json'
store.init()

checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


try:
    os.environ['TANDEM_COMPACT_WRITES'] = '1'
    os.environ['TANDEM_WEB_CHECK'] = '0'

    # 1. Real sequence: write_file -> compaction -> read_file range & full -> replace_in_file -> finish with verified citation
    proj = tmp / 'proj1'
    proj.mkdir()
    big_lines = [f'def fn_{i}():\n    return {i}\n' for i in range(30)]
    big_code = ''.join(big_lines) + 'def target():\n    return 1\n'

    fake = SlowFake(delay_s=0.01)
    engine.connect(url=fake.url)
    fake.script = [
        ('write_file', {'path': 'mod.py', 'content': big_code}),
        ('write_file', {'path': 'helper.py', 'content': 'x = 0\n' + 'x = 1\n' * 99}),
        # Now mod.py write_file is > 2 messages old, so it is compacted in view_messages!
        ('read_file', {'path': 'mod.py', 'start': 58, 'end': 62}),
        ('read_file', {'path': 'mod.py'}),
        ('replace_in_file', {'path': 'mod.py', 'old': 'def target():\n    return 1', 'new': 'def target():\n    return 42'}),
        # Modify helper.py a second time after its first write_file, then read it back
        ('replace_in_file', {'path': 'helper.py', 'old': 'x = 0\n', 'new': 'x = 99\n'}),
        ('read_file', {'path': 'helper.py', 'start': 1, 'end': 3}),
        ('finish', {'summary': 'updated target', 'evidence': [{'constraint': 1, 'path': 'mod.py', 'quote': 'return 42'}]}),
    ]

    seen_views = []
    orig_chat = engine.chat
    def _spy(msgs, **kw):
        seen_views.append(msgs)
        return orig_chat(msgs, **kw)

    (store.JOBS / 'job-compact-seq').mkdir(parents=True, exist_ok=True)
    t = agent.Task(
        'job-compact-seq', store.JOBS / 'job-compact-seq',
        'Create mod.py and update target() to return 42',
        sandbox.Workspace(str(proj), ['mod.py', 'helper.py'], [], []),
        verify=[f'{sys.executable} -c "import mod; assert mod.target()==42"'],
        max_steps=12, max_repairs=1, baseline=True,
        constraints=['mod.py target() returns 42'], require_proof=True,
    )
    engine.chat = _spy
    try:
        st = t.run()
    finally:
        engine.chat = orig_chat

    ok(st == 'verified', f'expected verified, got {st}')
    # Verify saved messages.json on disk still has full original write_file content (audit preserved)
    saved_msgs = store.read_json(store.JOBS / 'job-compact-seq' / 'messages.json', [])
    def _wf_content(tc):
        try:
            return json.loads(tc.get('function', {}).get('arguments') or '{}').get('content', '')
        except (ValueError, AttributeError):
            return ''
    ok(any(_wf_content(tc) == big_code
           for m in saved_msgs for tc in (m.get('tool_calls') or [])),
       'messages.json must preserve uncompacted write_file arguments for audit')
    # Verify seen_views later turns actually compacted mod.py write_file
    last_view_str = json.dumps(seen_views[-1])
    ok('[compacted persisted write_file: mod.py' in last_view_str and big_code[:200] not in last_view_str,
       'last view sent to model must compact mod.py write_file')
    # Verify read_file after compaction returned actual numbered lines from disk, NOT "[unchanged ..."
    read_tool_msgs = [m['content'] for m in saved_msgs if m.get('role') == 'tool' and 'def target()' in str(m.get('content'))]
    ok(len(read_tool_msgs) >= 2 and all('[unchanged' not in c for c in read_tool_msgs),
       f'read_file after compaction must return lines from disk, got {read_tool_msgs}')
    helper_reads = [m['content'] for m in saved_msgs if m.get('role') == 'tool' and '1| x = 99' in str(m.get('content'))]
    ok(len(helper_reads) == 2 and helper_reads[-1].startswith('1| x = 99'), f'expected modified helper.py line 1| x = 99 from disk, got {helper_reads}')

    # 2. Resume job with compaction active
    fake_res = SlowFake(delay_s=0.01)
    engine.connect(url=fake_res.url)
    fake_res.script = [
        ('read_file', {'path': 'mod.py', 'start': 60, 'end': 62}),
        ('finish', {'summary': 'resumed ok', 'evidence': [{'constraint': 1, 'path': 'mod.py', 'quote': 'return 42'}]}),
    ]
    d = store.read_job('job-compact-seq')
    d['state'] = 'stopped'
    d.setdefault('kind', 'delegate')  # the Task was built directly, not through agent.start()
    store.write_job('job-compact-seq', d)
    agent.resume('job-compact-seq', 'Double check target() line and finish')
    agent.RUNNING['job-compact-seq'][0].join(10)
    ok((store.read_job('job-compact-seq') or {}).get('state') == 'verified', 'resumed job must verify cleanly')

    # 3. JSON-fallback (native=False) compaction preserves valid JSON
    j_msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': 'task'},
        {'role': 'assistant', 'content': json.dumps({'tool': 'write_file', 'arguments': {'path': 'a.js', 'content': 'const x = 1;\n' * 60}})},
        {'role': 'user', 'content': 'Result of write_file:\nwrote a.js (60 lines, 780 bytes)\n1| const x = 1;\n'},
        {'role': 'assistant', 'content': json.dumps({'tool': 'list_files', 'arguments': {'glob': '*'}})},
        {'role': 'user', 'content': 'Result of list_files:\na.js'},
    ]
    j_view, j_paths = agent._compact_messages_view(j_msgs)
    ok('a.js' in j_paths, f'expected a.js in compacted paths: {j_paths}')
    parsed_asst = json.loads(j_view[2]['content'])
    ok(parsed_asst['tool'] == 'write_file' and '[compacted persisted write_file: a.js' in parsed_asst['arguments']['content'],
       f'JSON fallback assistant message must remain valid JSON: {parsed_asst}')
    ok('[compacted write_file output: a.js' in j_view[3]['content'], f'JSON fallback tool output must compact: {j_view[3]}')

    # 4. The executor copying a placeholder as file content is refused and the file stays intact
    before = (proj / 'mod.py').read_text()
    stub = '[compacted persisted write_file: mod.py, lines 1..40, sha256=deadbeef; use read_file(path, start, end) to inspect]'
    res_stub = t.call('write_file', {'path': 'mod.py', 'content': stub})
    ok(res_stub.startswith('ERROR: refused') and (proj / 'mod.py').read_text() == before,
       f'stub write must be refused and leave the file unchanged: {res_stub}')

    print(f'{checks} checks, 0 failures')
finally:
    os.environ.pop('TANDEM_WEB_CHECK', None)
    shutil.rmtree(tmp, ignore_errors=True)
