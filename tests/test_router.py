"""Offline unit tests for tandem_mcp.router and server.auto_route."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ['TANDEM_PROFILE'] = 'lean'
from tandem_mcp import router, server, store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_router_test_'))
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
    # 1. Small workspace -> direct_or_targeted for short explain / small edit
    ws_small = tmp / 'ws_small'
    ws_small.mkdir()
    (ws_small / 'cache.py').write_text('def get(k):\n    return None\n', encoding='utf-8')
    d_exp = router.classify_request('usa Tandem: spiega come funziona cache.py', ws_small, budget_seconds=180)
    ok(d_exp['route'] == 'direct_or_targeted', f'expected direct_or_targeted for small explain, got {d_exp}')
    d_edit = router.classify_request('usa Tandem: correggi il valore di ritorno in cache.py', ws_small, budget_seconds=180)
    ok(d_edit['route'] == 'direct_or_targeted', f'expected direct_or_targeted for small edit, got {d_edit}')

    # 2. Structured extraction -> deterministic
    ws_ext = tmp / 'ws_ext'
    ws_ext.mkdir()
    (ws_ext / 'metrics.json').write_text('{"items": [1, 2, 3]}\n', encoding='utf-8')
    d_det = router.classify_request('usa Tandem: estrai la somma esatta di items da metrics.json', ws_ext, budget_seconds=120)
    ok(d_det['route'] == 'deterministic', f'expected deterministic, got {d_det}')

    # 3. Large read (>=20KB) -> delegate_local
    ws_large = tmp / 'ws_large'
    ws_large.mkdir()
    (ws_large / 'big.py').write_text('# line\n' * 3500, encoding='utf-8')
    d_big = router.classify_request('usa Tandem: spiega la gestione errori in big.py', ws_large, budget_seconds=300)
    ok(d_big['route'] == 'delegate_local', f'expected delegate_local for large read, got {d_big}')

    # 4. Medium refactor on existing code (<40KB, <=10 files) -> direct_or_targeted; from-scratch gen -> delegate_local
    ws_multi = tmp / 'ws_multi'
    ws_multi.mkdir()
    for i in range(4):
        (ws_multi / f'm{i}.py').write_text('def f():\n    return 1\n' * 150, encoding='utf-8')
    d_ref = router.classify_request('usa Tandem: rinomina f in compute su più file mantenendo i test verdi', ws_multi, budget_seconds=480)
    ok(d_ref['route'] == 'direct_or_targeted', f'expected direct_or_targeted for medium existing-code refactor, got {d_ref}')

    # 4b. Plain `usa Tandem` (budget absent OR explicit budget alone) -> direct_or_targeted for medium generation
    d_gen_plain_nobudget = router.classify_request('usa Tandem: crea da zero un modulo parser markdown con test unitari', ws_small)
    ok(d_gen_plain_nobudget['route'] == 'direct_or_targeted' and d_gen_plain_nobudget['signals']['budget_absent'] is True,
       f'plain usa Tandem without budget must stay direct, got {d_gen_plain_nobudget}')
    d_gen_plain_300 = router.classify_request('usa Tandem: crea da zero un modulo parser markdown con test unitari', ws_small, budget_seconds=300)
    ok(d_gen_plain_300['route'] == 'direct_or_targeted' and d_gen_plain_300['signals']['budget_absent'] is False and d_gen_plain_300['signals']['budget_seconds'] == 300,
       f'explicit 300s budget alone must stay direct and record budget_absent=False, got {d_gen_plain_300}')
    d_gen_plain_900 = router.classify_request('usa Tandem: crea da zero un modulo parser markdown con test unitari', ws_small, budget_seconds=900)
    ok(d_gen_plain_900['route'] == 'direct_or_targeted', f'explicit 900s budget alone must not trigger delegation, got {d_gen_plain_900}')

    # 4c. Explicit cloud-savings preference -> delegate_local for verifiable from-scratch gen (budget absent or sufficient)
    for phrase in [
        'usa Tandem, privilegia il risparmio di token cloud, posso aspettare: crea da zero un modulo parser markdown con test unitari',
        'usa Tandem, privilegia il risparmio cloud: crea da zero un modulo parser markdown con test unitari',
        'usa Tandem, risparmia token cloud, posso aspettare: crea da zero un modulo parser markdown con test unitari',
        'usa Tandem, preferisci il risparmio cloud: crea da zero un modulo parser markdown con test unitari',
        'usa Tandem, meno token cloud: crea da zero un modulo parser markdown con test unitari',
    ]:
        d_save = router.classify_request(phrase, ws_small)
        ok(d_save['route'] == 'delegate_local' and d_save['constraints']['prefer_cloud_savings'] is True and d_save['signals']['budget_absent'] is True,
           f'cloud-savings phrase should delegate without budget: {phrase} -> {d_save}')
    d_save_tight = router.classify_request('usa Tandem, privilegia il risparmio di token cloud: crea da zero index.html con canvas interattivo', ws_small, budget_seconds=300)
    ok(d_save_tight['route'] == 'direct_or_targeted', f'web gen with tight 300s budget must stay direct, got {d_save_tight}')
    d_save_web_nobudget = router.classify_request('usa Tandem, privilegia il risparmio di token cloud, posso aspettare: crea da zero index.html con canvas interattivo', ws_small)
    ok(d_save_web_nobudget['route'] == 'delegate_local', f'web gen with cloud-savings and no budget should delegate, got {d_save_web_nobudget}')

    # 4d. Targeted edit to existing code with existing tests -> direct_or_targeted even with cloud-savings preference
    d_save_edit = router.classify_request(
        'usa Tandem, privilegia il risparmio di token cloud, posso aspettare: modifica cache.py mantenendo verdi i test già presenti',
        ws_small,
    )
    ok(d_save_edit['route'] == 'direct_or_targeted', f'targeted existing-code edit with cloud-savings must stay direct, got {d_save_edit}')

    # 5. Explicit constraints: "solo locale" & "non modificare file"
    d_local = router.classify_request('usa Tandem solo locale: spiega cache.py e non modificare file', ws_small, budget_seconds=180)
    ok(d_local['route'] == 'delegate_local' and d_local['constraints']['local_only'] and d_local['constraints']['read_only'],
       f'explicit constraints not honored: {d_local}')
    ok(not d_local['signals']['is_write'], 'read_only must suppress is_write')

    # 6. Fallback logic: local_only blocks cloud fallback; partial edit triggers inspect_partial_or_rollback
    fb_block = router.evaluate_fallback(route_used='digest_file', outcome='timeout', local_only=True, remaining_budget_s=100.0)
    ok(fb_block['fallback'] == 'none_blocked_local_only', f'local_only must block cloud fallback: {fb_block}')
    fb_read = router.evaluate_fallback(route_used='digest_file', outcome='timeout', local_only=False, remaining_budget_s=60.0)
    ok(fb_read['fallback'] == 'targeted_cloud_read', f'expected targeted_cloud_read: {fb_read}')

    (store.JOBS / 'job-partial').mkdir(parents=True, exist_ok=True)
    store.write_job('job-partial', {'job': 'job-partial', 'state': 'out_of_time', 'changes': [['a.py', 'edit', 5, 1]], 'backup_status': 'fully_backed'})
    fb_part = router.evaluate_fallback(route_used='delegate', outcome='timeout', local_only=False, remaining_budget_s=120.0, job_id='job-partial')
    ok(fb_part['fallback'] == 'inspect_partial_or_rollback' and fb_part['changed_files'] == ['a.py'], f'expected inspect_partial: {fb_part}')

    # 7. MCP tool auto_route exposed in lean profile and logs to router_log.jsonl
    tool_names = [t.name for t in server.mcp._tool_manager.list_tools()]
    ok('auto_route' in tool_names, f'auto_route missing in lean tools: {tool_names}')
    res_json = json.loads(server.auto_route('usa Tandem: spiega cache.py', str(ws_small), budget_seconds=180))
    ok(res_json['route'] == 'direct_or_targeted', f'server.auto_route mismatch: {res_json}')
    ok((store.DATA / 'router_log.jsonl').is_file(), 'router_log.jsonl must be written')

    print(f'{checks} checks, 0 failures')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
