"""Concurrency, workspace lease, and child-process cancellation tests (P02, P03, P04)."""
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _worker_save_cap(tandem_home: str, key: str, val: dict):
    os.environ['TANDEM_HOME'] = tandem_home
    from tandem_mcp import store
    for _ in range(10):
        store.save_model_caps(key, val)


def _worker_hold_lease(tandem_home: str, ws: str, ready_q, crash: bool = False):
    os.environ['TANDEM_HOME'] = tandem_home
    from tandem_mcp import store
    h = store.acquire_workspace_lease(ws, owner_id='worker', wait_seconds=0.0)
    ready_q.put('acquired')
    if crash:
        time.sleep(0.05)
        os._exit(1)
    time.sleep(0.8)
    store.release_workspace_lease(h)


class P02StoreConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ['TANDEM_HOME'] = self.home
        # Reload store paths for this TANDEM_HOME
        import importlib
        from tandem_mcp import store
        importlib.reload(store)
        self.store = store

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_two_processes_preserve_both_model_capabilities(self):
        ctx = multiprocessing.get_context('spawn')
        p1 = ctx.Process(target=_worker_save_cap, args=(self.home, 'url|modelA', {'tools': True}))
        p2 = ctx.Process(target=_worker_save_cap, args=(self.home, 'url|modelB', {'schema': True}))
        p1.start()
        p2.start()
        p1.join(timeout=10)
        p2.join(timeout=10)
        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)
        self.assertEqual(self.store.model_caps('url|modelA'), {'tools': True})
        self.assertEqual(self.store.model_caps('url|modelB'), {'schema': True})

    def test_ledger_append_during_trim_preserves_records(self):
        self.store.init()
        # Seed old + recent entries
        old_line = json.dumps({'ts': 100.0, 'tool': 'old'})
        self.store.LEDGER.write_text(old_line + '\n')
        errors = []

        def writer():
            try:
                for i in range(30):
                    self.store.log('digest_file', seq=i)
            except Exception as exc:
                errors.append(exc)

        def trimmer():
            try:
                for _ in range(15):
                    self.store._trim_ledger(1)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=trimmer)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)
        self.assertEqual(errors, [])
        seqs = {r['seq'] for r in self.store.ledger(30) if 'seq' in r}
        self.assertEqual(seqs, set(range(30)))

    def test_lesson_add_during_drop_preserves_new_lesson(self):
        self.store.init()
        self.store.add_lesson('/proj', 'drop-me rule 1')
        self.store.add_lesson('/proj', 'drop-me rule 2')
        self.store.drop_lesson('/proj', 'drop-me')
        self.store.add_lesson('/proj', 'keep-me rule')
        rows = self.store.lessons('/proj', 50)
        self.assertEqual([r['text'] for r in rows], ['keep-me rule'])


class P03WorkspaceLeaseTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.ws1 = tempfile.mkdtemp()
        self.ws2 = tempfile.mkdtemp()
        os.environ['TANDEM_HOME'] = self.home
        import importlib
        from tandem_mcp import store
        importlib.reload(store)
        self.store = store

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.ws1, ignore_errors=True)
        shutil.rmtree(self.ws2, ignore_errors=True)

    def test_same_workspace_blocks_concurrent_writer_while_distinct_succeeds(self):
        ctx = multiprocessing.get_context('spawn')
        q = ctx.Queue()
        p = ctx.Process(target=_worker_hold_lease, args=(self.home, self.ws1, q, False))
        p.start()
        try:
            self.assertEqual(q.get(timeout=10), 'acquired')
            with self.assertRaises(self.store.WorkspaceBusyError):
                self.store.acquire_workspace_lease(self.ws1, owner_id='parent', wait_seconds=0.1)
            # Distinct workspace must succeed immediately
            h2 = self.store.acquire_workspace_lease(self.ws2, owner_id='parent', wait_seconds=0.1)
            self.store.release_workspace_lease(h2)
        finally:
            p.join(timeout=10)

    def test_lease_recovers_after_worker_crash(self):
        ctx = multiprocessing.get_context('spawn')
        q = ctx.Queue()
        p = ctx.Process(target=_worker_hold_lease, args=(self.home, self.ws1, q, True))
        p.start()
        self.assertEqual(q.get(timeout=10), 'acquired')
        p.join(timeout=10)
        # Kernel releases flock on crash -> next acquire succeeds
        h = self.store.acquire_workspace_lease(self.ws1, owner_id='after_crash', wait_seconds=0.2)
        self.store.release_workspace_lease(h)


class P04CancellationTests(unittest.TestCase):
    def test_stop_event_kills_child_process_group_within_threshold(self):
        from tandem_mcp import sandbox
        ws = Path(tempfile.mkdtemp())
        try:
            ev = threading.Event()
            marker = f'tandem_p04_marker_{os.getpid()}'
            timer = threading.Timer(0.25, ev.set)
            timer.start()
            t0 = time.monotonic()
            code, out = sandbox.run(
                f'python3 -c "import time; time.sleep(30)" #{marker}',
                ws,
                timeout=30,
                jail=False,
                stop_event=ev,
            )
            elapsed = time.monotonic() - t0
            timer.cancel()
            self.assertEqual(code, 130)
            self.assertIn('[stopped by request]', out)
            self.assertLess(elapsed, 2.5)
            # Verify no child process with marker remains alive
            ps = subprocess.run(['pgrep', '-f', marker], capture_output=True, text=True)
            self.assertNotEqual(ps.returncode, 0, f'orphan process remained: {ps.stdout}')
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
