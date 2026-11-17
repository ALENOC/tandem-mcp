"""Transparent stdio JSON-RPC proxy for measuring actual MCP tool payloads.

Forwards stdin/stdout byte-for-byte between the MCP client (agy) and the pinned
Tandem MCP v3.6.1 server without modifying any Tandem code, while logging every
`tools/call` request/response payload size and truncation status to BENCH_MCP_LOG.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        sys.exit(2)
    target_cmd = sys.argv[1:]
    log_path = os.environ.get('BENCH_MCP_LOG', '')
    lock = threading.Lock()
    pending: dict[str, dict] = {}

    proc = subprocess.Popen(
        target_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )
    assert proc.stdin is not None and proc.stdout is not None

    def _append_log(entry: dict):
        if not log_path:
            return
        with lock:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')

    def _pump_in():
        try:
            for raw in sys.stdin.buffer:
                try:
                    msg = json.loads(raw.decode('utf-8', errors='replace'))
                    if isinstance(msg, dict) and msg.get('method') == 'tools/call' and 'id' in msg:
                        params = msg.get('params') or {}
                        with lock:
                            pending[str(msg['id'])] = {
                                'tool_name': params.get('name', 'unknown'),
                                'request_bytes': len(raw),
                            }
                except Exception:
                    pass
                proc.stdin.write(raw)
                proc.stdin.flush()
        except Exception:
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    def _pump_out():
        try:
            for raw in proc.stdout:
                try:
                    msg = json.loads(raw.decode('utf-8', errors='replace'))
                    if isinstance(msg, dict) and 'id' in msg:
                        with lock:
                            req = pending.pop(str(msg['id']), None)
                        if req is not None:
                            result = msg.get('result') or {}
                            content = result.get('content') or []
                            text = ''.join(str(c.get('text', '')) for c in content if isinstance(c, dict))
                            truncated = ('truncated' in text.lower()) or ('omitted' in text.lower())
                            _append_log({
                                'tool_name': req['tool_name'],
                                'request_bytes': req['request_bytes'],
                                'response_bytes': len(raw),
                                'response_text_bytes': len(text.encode('utf-8', errors='replace')),
                                'truncated': truncated,
                            })
                except Exception:
                    pass
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
        except Exception:
            pass

    t_in = threading.Thread(target=_pump_in, daemon=True)
    t_out = threading.Thread(target=_pump_out, daemon=True)
    t_in.start()
    t_out.start()
    t_in.join()
    t_out.join()
    sys.exit(proc.wait())


if __name__ == '__main__':
    main()
