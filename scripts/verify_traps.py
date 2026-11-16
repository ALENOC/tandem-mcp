import os, sys, time, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()   # PRIMA degli import
from tandem_mcp import sandbox, store, agent, server
root = pathlib.Path(tempfile.mkdtemp())

# 1. output sotto cap ma sopra head_cap: la coda ci deve essere, senza marker
code, out = sandbox.run('python3 -c "print(\'A\'*1500); print(\'ENDMARK\')"', root, max_output_bytes=4096)
assert code == 0 and 'ENDMARK' in out and '[output truncated:' not in out, out[-200:]

# 2. troncamento: head + marker + tail
code, out = sandbox.run('python3 -c "print(\'H\'*5000); print(\'M\'*5000); print(\'TAILMARK\')"', root, max_output_bytes=4096)
assert 'TAILMARK' in out and '[output truncated:' in out and out.startswith('H')

# 3. anti-hang: il figlio DEVE sopravvivere al killpg (fork prima, cosi non e group leader)
t0 = time.time()
code, out = sandbox.run('python3 -c "import os,time; pid=os.fork(); (os.setsid(), time.sleep(5)) if pid==0 else time.sleep(5)"', root, timeout=1)
assert code == 124 and time.time() - t0 < 8, (code, round(time.time()-t0, 1))

# 4. redaction choke point + falsi positivi
assert '[REDACTED' in server._saved('digest_file', 10, 'OPENAI_API_KEY=sk-proj-1234567890abcdefghijklmnop')
assert 'MONKEY_COUNT=5' in server._saved('x', 10, 'MONKEY_COUNT=5')
assert '[REDACTED' in server._fail(ValueError('Authorization: Bearer abcdefghijklmnopqrstuvwxyz'))

# 5. SECRETS mirate
assert '.m2/settings.xml' in sandbox.SECRETS and '.m2' not in sandbox.SECRETS
assert '.gradle/gradle.properties' in sandbox.SECRETS and '.gradle' not in sandbox.SECRETS

# 6. request_stop su job morto: nessun evento stray
assert agent.request_stop('dead-job') is False and 'dead-job' not in agent.STOP

# 7. cache stamp disattivata su nt
old = sandbox.os.name
try:
    sandbox.os.name = 'nt'
    sandbox.stamp(root)
    assert os.fspath(root) not in sandbox._STAMP_CACHE
finally:
    sandbox.os.name = old

# 8. grace period reconcile
j, _ = store.new_job('delegate')
store.reconcile_stale_jobs()
assert store.read_job(j)['state'] == 'running'
print('OK: 8 trap verificate')
