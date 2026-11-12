"""A task done by the local executor under a contract set by the orchestrator.

The contract: a workspace, the files that may be written, the commands that may be run and the
checks that decide whether the work is accepted. The executor works with tools; every file it
changes is journalled, so the task can be shown as a diff and undone. When the executor says it
has finished, the checks run; their failures go back to the executor, up to a number of repairs.
The orchestrator receives a short receipt, never the transcript."""
import difflib
import json
import re
import threading
import time
from pathlib import Path

from . import engine, sandbox, store

TOOLS = [
    ('list_files', 'List files of the workspace that match a glob such as "src/*.c" or "*.md".',
     {'glob': {'type': 'string'}}, ['glob']),
    ('read_file', 'Read a text file, optionally only lines start..end. Lines come back numbered.',
     {'path': {'type': 'string'}, 'start': {'type': 'integer'}, 'end': {'type': 'integer'}}, ['path']),
    ('search', 'Search a regular expression in the files that match a glob. Returns path:line: text.',
     {'pattern': {'type': 'string'}, 'glob': {'type': 'string'}}, ['pattern']),
    ('replace_in_file', 'Replace one exact occurrence of old with new in a file. old must be unique in the file.',
     {'path': {'type': 'string'}, 'old': {'type': 'string'}, 'new': {'type': 'string'}}, ['path', 'old', 'new']),
    ('write_file', 'Create a file or replace its whole content.',
     {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ['path', 'content']),
    ('run', 'Run a shell command in the workspace (only commands the task allows).',
     {'command': {'type': 'string'}}, ['command']),
    ('finish', 'Declare the task finished. summary: what was done, in at most 60 words. '
               'Set blocked to true when the task cannot be done and say why.',
     {'summary': {'type': 'string'}, 'blocked': {'type': 'boolean'}}, ['summary']),
]
SPEC = [{'type': 'function', 'function': {'name': n, 'description': d,
                                          'parameters': {'type': 'object', 'properties': p, 'required': r}}}
        for n, d, p, r in TOOLS]
SYSTEM = '''You are the executor of an engineering team. A senior engineer gave you one task and will check it.
Rules:
- Work only through the tools. Read before you change. Make the smallest change that does the task.
- Do not touch anything the task does not ask for. Keep the style of the file.
- Never use em dashes or en dashes in anything you write.
- When the work is done call finish. If something blocks you, call finish with blocked true and the reason.
- Checks run after finish. If they fail you get their output: fix the cause, then call finish again.'''
OUT_CAP = 6000


class Task:
    def __init__(self, job, folder, goal, workspace, verify, max_steps, max_repairs, model, context):
        self.job, self.folder, self.goal, self.ws = job, folder, goal, workspace
        self.verify, self.max_steps, self.max_repairs, self.model = verify, max_steps, max_repairs, model
        self.context = context
        self.journal = {}                  # relative path -> original text, None when the file was created
        self.steps = self.tokens = self.read_chars = 0
        self.log = []

    # tools of the executor -------------------------------------------------------------------
    def _remember(self, p):
        rel = self.ws.rel(p)
        if rel not in self.journal:
            self.journal[rel] = p.read_text(errors='replace') if p.exists() else None
            (self.folder / 'journal.json').write_text(json.dumps(self.journal))

    def call(self, name, args):
        if name == 'list_files':
            files = sandbox.walk(self.ws.root, args.get('glob') or '*', 300)
            return '\n'.join(files) or '(no file matches)'
        if name == 'read_file':
            text = sandbox.read_text(self.ws.path(args['path']))
            lines = text.splitlines()
            start = max(1, int(args.get('start') or 1))
            end = min(len(lines), int(args.get('end') or len(lines)))
            body = '\n'.join(f'{n}| {lines[n - 1]}' for n in range(start, end + 1))
            self.read_chars += len(body)
            if len(body) > 4 * OUT_CAP:
                body = body[:4 * OUT_CAP] + f'\n[cut: the file has {len(lines)} lines, read a range]'
            return body or '(empty)'
        if name == 'search':
            rx = re.compile(args['pattern'])
            out = []
            for rel in sandbox.walk(self.ws.root, args.get('glob') or '*', 2000):
                try:
                    text = sandbox.read_text(self.ws.root / rel, 600_000)
                except Exception:
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if rx.search(line):
                        out.append(f'{rel}:{n}: {line.strip()[:160]}')
                        if len(out) >= 80:
                            return '\n'.join(out) + '\n[more matches cut]'
            return '\n'.join(out) or '(no match)'
        if name == 'replace_in_file':
            p = self.ws.writable(args['path'])
            text = p.read_text(errors='replace')
            count = text.count(args['old'])
            if count != 1:
                return f'ERROR: old text found {count} times, it must be found exactly once. Read the file and copy it exactly.'
            self._remember(p)
            p.write_text(text.replace(args['old'], args['new']))
            return 'replaced'
        if name == 'write_file':
            p = self.ws.writable(args['path'])
            self._remember(p)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'])
            return f'written, {len(args["content"].splitlines())} lines'
        if name == 'run':
            self.ws.check_command(args['command'])
            code, out = sandbox.run(args['command'], self.ws.root)
            return f'exit {code}\n' + (out[-OUT_CAP:] if len(out) > OUT_CAP else out)
        return f'ERROR: unknown tool {name}'

    # results ---------------------------------------------------------------------------------
    def diff(self, only=''):
        out = []
        for rel, before in sorted(self.journal.items()):
            if only and rel != only:
                continue
            p = self.ws.root / rel
            after = p.read_text(errors='replace') if p.exists() else ''
            out += list(difflib.unified_diff((before or '').splitlines(), after.splitlines(),
                                             f'a/{rel}' if before is not None else '/dev/null', f'b/{rel}', lineterm='', n=2))
        return '\n'.join(out)

    def changes(self):
        rows = []
        for rel, before in sorted(self.journal.items()):
            p = self.ws.root / rel
            after = p.read_text(errors='replace') if p.exists() else ''
            if before == after:
                continue
            sm = difflib.SequenceMatcher(None, (before or '').splitlines(), after.splitlines(), autojunk=False)
            add = sum(j2 - j1 for tag, _, _, j1, j2 in sm.get_opcodes() if tag in ('replace', 'insert'))
            rem = sum(i2 - i1 for tag, i1, i2, _, _ in sm.get_opcodes() if tag in ('replace', 'delete'))
            rows.append((rel, 'new' if before is None else 'changed', add, rem))
        return rows

    def run_checks(self):
        results = []
        for command in self.verify:
            code, out = sandbox.run(command, self.ws.root, 900)
            results.append({'command': command, 'exit': code, 'tail': out.strip()[-1500:]})
        return results

    # the loop --------------------------------------------------------------------------------
    def run(self):
        notes = store.lessons(store.scope_of(self.ws.root))
        system = SYSTEM
        if notes:
            system += '\nLessons from earlier reviews of your work in this project:\n' + '\n'.join(f'- {n["text"]}' for n in notes)
        rules = [f'Workspace: {self.ws.root}']
        rules.append('Writable files: ' + (', '.join(self.ws.write_globs) if self.ws.write_globs else 'any file of the workspace'))
        rules.append('Commands you may run: ' + (', '.join(r.pattern for r in self.ws.allow_run) if self.ws.allow_run else 'none'))
        if self.verify:
            rules.append('Checks that will run after finish: ' + ' ; '.join(self.verify))
        user = f'Task: {self.goal}\n\n' + '\n'.join(rules)
        if self.context:
            user += f'\n\nContext from the senior engineer:\n{self.context}'
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        repairs, summary, state, checks = 0, '', 'out_of_steps', []
        budget = int(engine.context_tokens(self.model or engine.default_model()) * 0.6 * 3.2)
        while self.steps < self.max_steps:
            self.steps += 1
            self._shrink(messages, budget)
            message, used = engine.chat(messages, tool='delegate', model=self.model, tools=SPEC, max_tokens=4000)
            self.tokens += used['prompt'] + used['completion']
            calls = message.tool_calls or []
            entry = {'role': 'assistant', 'content': message.content or ''}
            if calls:
                entry['tool_calls'] = [{'id': c.id, 'type': 'function',
                                        'function': {'name': c.function.name, 'arguments': c.function.arguments}} for c in calls]
            messages.append(entry)
            if not calls:
                messages.append({'role': 'user', 'content': 'Use a tool. Call finish when the task is done.'})
                continue
            finished = None
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or '{}')
                except ValueError:
                    args, result = {}, 'ERROR: arguments are not valid JSON'
                else:
                    if c.function.name == 'finish':
                        finished, result = args, 'noted'
                    else:
                        try:
                            result = self.call(c.function.name, args)
                        except (sandbox.SandboxError, OSError, KeyError, re.error, UnicodeError) as exc:
                            result = f'ERROR: {exc}'
                self.log.append({'step': self.steps, 'tool': c.function.name,
                                 'args': {k: (v if len(str(v)) < 200 else str(v)[:200] + '...') for k, v in args.items()},
                                 'result': result[:300]})
                messages.append({'role': 'tool', 'tool_call_id': c.id, 'content': result})
            (self.folder / 'log.json').write_text(json.dumps(self.log, indent=1))
            self._save('running', summary, checks)
            if finished is None:
                continue
            summary = str(finished.get('summary', ''))[:600]
            if finished.get('blocked'):
                state = 'blocked'
                break
            checks = self.run_checks()
            failed = [c for c in checks if c['exit'] != 0]
            if not failed:
                state = 'verified' if checks else 'unverified'
                break
            if repairs >= self.max_repairs:
                state = 'checks_failed'
                break
            repairs += 1
            messages.append({'role': 'user', 'content': 'The checks failed. Fix the cause and call finish again.\n' + '\n'.join(
                f'$ {c["command"]}\nexit {c["exit"]}\n{c["tail"]}' for c in failed)})
        self._save(state, summary, checks, repairs)
        return state

    def _shrink(self, messages, budget):
        """Old tool results are cut first when the conversation outgrows the context."""
        size = sum(len(str(m.get('content', ''))) + len(json.dumps(m.get('tool_calls', ''))) for m in messages)
        for m in messages[2:-6]:
            if size <= budget:
                break
            if m['role'] == 'tool' and len(m['content']) > 200:
                size -= len(m['content']) - 60
                m['content'] = m['content'][:40] + ' [older output dropped]'

    def _save(self, state, summary, checks, repairs=0):
        data = store.read_job(self.job) or {}
        data.update(state=state, summary=summary, checks=checks, repairs=repairs, steps=self.steps, tokens=self.tokens,
                    read_chars=self.read_chars, workspace=str(self.ws.root), goal=self.goal,
                    changes=self.changes(), seconds=round(time.time() - data.get('started', time.time()), 1))
        store.write_job(self.job, data)


RUNNING = {}


def start(goal, workspace, verify, max_steps, max_repairs, model, context):
    job, folder = store.new_job('delegate')
    task = Task(job, folder, goal, workspace, verify, max_steps, max_repairs, model, context)

    def body():
        try:
            state = task.run()
        except Exception as exc:                 # the receipt must exist whatever happens
            task._save('error', f'{type(exc).__name__}: {exc}', [])
            state = 'error'
        diff = task.diff()
        (folder / 'changes.diff').write_text(diff)
        store.log('delegate', kind='result', job=job, state=state, steps=task.steps, executor_tokens=task.tokens,
                  bytes_in=task.read_chars + len(diff), bytes_out=0)

    thread = threading.Thread(target=body, daemon=True)
    RUNNING[job] = (thread, task)
    thread.start()
    return job


def rollback(job):
    """Put back every file the task changed, to its content before the task."""
    folder = store.JOBS / job
    data = store.read_job(job)
    if not data or not (folder / 'journal.json').exists():
        return 'no journal for this job'
    journal = json.loads((folder / 'journal.json').read_text())
    root = Path(data['workspace'])
    done = []
    for rel, before in journal.items():
        p = root / rel
        if before is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(before)
        done.append(rel)
    data['state'] = 'rolled_back'
    store.write_job(job, data)
    return 'restored: ' + (', '.join(done) or 'nothing')
