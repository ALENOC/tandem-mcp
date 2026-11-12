"""Tandem MCP server: a cloud orchestrator model and a local executor model (LM Studio).

The orchestrator keeps the decisions and the final check; the local model does the reading and
the mechanical work on the machine and reports in a few lines. Three ideas shape the tools:

1. Contracts. `delegate` gives the executor a workspace, write and command limits and the checks
   that decide acceptance. The server runs the checks itself and returns a receipt.
2. Checked evidence. `digest_*` answers come with quotes that the server looks up in the source;
   a quote that is not there is dropped and reported, so a made-up answer is visible.
3. Supervised memory. The verdict of the orchestrator on a job becomes a lesson that the executor
   reads at its next task in that project, and the ledger shows where delegation pays.
"""
import json
import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from tandem import agent, digest, engine, sandbox, store

GUIDE = '''Local executor (a model on this machine, free to use). Prefer it for reading and mechanical work:
- digest_file / digest_command / digest_many: ask a question about a file, a command output or many files
  instead of reading them. Answers carry quotes checked against the source.
- extract_from_file: structured data in a JSON schema.
- delegate: a bounded task with checks (tests, build, grep). Review the receipt, job_diff if needed,
  then job_feedback (accepted or not, with a lesson) or job_rollback.
- ask: a text task; samples > 1 gives an agreement score, low agreement means do it yourself.
Keep design decisions, irreversible actions and anything without an automatic check for yourself.'''
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
mcp = MCPServer('tandem-local-executor', version='2.0.0', instructions=GUIDE)


def _fail(exc):
    return f'ERROR: {exc}'


def _saved(tool, bytes_in, text, **more):
    store.log(tool, kind='result', bytes_in=bytes_in, bytes_out=len(text), **more)
    return text


# status ----------------------------------------------------------------------------------------
@mcp.tool()
def executor_status() -> str:
    """State of the local executor: models, which one is loaded, its context length."""
    try:
        rows = engine.models()
        active = engine.default_model()
    except Exception as exc:
        return f'LM Studio not reachable at {engine.BASE_URL}: {exc}'
    lines = [f'LM Studio online at {engine.BASE_URL}', f'executor model: {active}']
    lines += [f'- {m["id"]}  {"loaded" if m["loaded"] else "not loaded"}  context {m["context"]}' for m in rows]
    return '\n'.join(lines)


@mcp.tool()
def check_lmstudio_status() -> str:
    """Same as executor_status (kept for existing instructions)."""
    return executor_status()


# plain text tasks ------------------------------------------------------------------------------
@mcp.tool()
def ask(prompt: str, system_prompt: str = '', json_schema: str = '', samples: int = 1, max_tokens: int = 3000,
        model: str = '') -> str:
    """A text task for the local executor (drafting, translation, boilerplate, classification).

    json_schema: optional JSON schema (as a string) that the answer must follow.
    samples: 2 to 5 runs the task several times and reports how many runs agree. Agreement
    below 1.0 on a factual or structured task means the executor is unsure: check or do it yourself."""
    try:
        schema = json.loads(json_schema) if json_schema.strip() else None
        messages = ([{'role': 'system', 'content': system_prompt}] if system_prompt.strip() else []) + \
                   [{'role': 'user', 'content': prompt}]
        answers = []
        for k in range(max(1, min(int(samples), 5))):
            temperature = 0.1 if k == 0 else 0.7
            if schema:
                data, _ = engine.chat_json(messages, schema, tool='ask', model=model, max_tokens=max_tokens, temperature=temperature)
                answers.append(data)
            else:
                message, _ = engine.chat(messages, tool='ask', model=model, max_tokens=max_tokens, temperature=temperature)
                answers.append((message.content or '').strip())
        if len(answers) == 1:
            text = answers[0] if isinstance(answers[0], str) else json.dumps(answers[0], indent=1)
            return _saved('ask', 0, text)
        share, best = digest.agreement(answers)
        text = best if isinstance(best, str) else json.dumps(best, indent=1)
        return _saved('ask', 0, f'[agreement {share:.2f} over {len(answers)} runs]\n{text}')
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def ask_local_qwen(prompt: str, system_prompt: str = '', model: str = '', max_tokens: int = 4096,
                   temperature: float = 0.2) -> str:
    """A text task for the local executor (older name of `ask`, one run, free text)."""
    try:
        messages = ([{'role': 'system', 'content': system_prompt}] if system_prompt.strip() else []) + \
                   [{'role': 'user', 'content': prompt}]
        message, _ = engine.chat(messages, tool='ask', model=model, max_tokens=max_tokens, temperature=temperature)
        return _saved('ask', 0, (message.content or '').strip())
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def generate_code_with_qwen(task_description: str, language: str = 'python', context_code: str = '') -> str:
    """Code written by the local executor from a precise description. Returns the code only.
    For a change inside a project prefer `delegate`, which edits the files and runs the checks."""
    try:
        prompt = f'Task: {task_description}\n'
        if context_code.strip():
            prompt += f'\nExisting code for context:\n{context_code}\n'
        prompt += '\nReturn only the code, no fences, no explanation.'
        message, _ = engine.chat(
            [{'role': 'system', 'content': f'You are a senior {language} programmer. Write complete, correct code. '
                                           'Comments in English, no em dashes.'},
             {'role': 'user', 'content': prompt}], tool='code', max_tokens=6000)
        text = (message.content or '').strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1] if '\n' in text else ''
            text = text.rsplit('```', 1)[0].rstrip()
        return _saved('code', len(context_code), text)
    except Exception as exc:
        return _fail(exc)


# reading for the orchestrator ------------------------------------------------------------------
@mcp.tool()
def digest_file(path: str, question: str, max_words: int = 120, grep: str = '') -> str:
    """Ask a question about a file (text, source, log, JSON, PDF) instead of reading it.

    The executor reads the whole file, in parts if it is long, and answers in at most max_words
    with line references and quotes. The server checks every quote against the file.
    grep: optional regular expression; only matching lines (with context) are read, which is
    faster on large files when you know what to look for."""
    try:
        text = sandbox.read_text(Path(path).expanduser())
        result = digest.answer(text, question, max_words, grep, tool='digest_file')
        out = digest.render(result, Path(path).name)
        return _saved('digest_file', len(text), out, executor_tokens=result['tokens'])
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def digest_command(command: str, cwd: str, question: str = '', max_words: int = 120, timeout: int = 600) -> str:
    """Run a command of yours (build, tests, linter, DRC) and get the verdict instead of the output.

    Returns the exit code, the answer of the executor to `question` (default: did it succeed,
    and what are the errors) with checked quotes, the last lines of the output, and the path
    of the full output in case you need to read a part yourself. The command runs as you wrote
    it, with your rights: the safety list applies only to commands the executor chooses."""
    try:
        job, folder = store.new_job('command')
        code, output = sandbox.run(command, Path(cwd).expanduser(), timeout)
        full = folder / 'output.txt'
        full.write_text(output)
        question = question or 'Did the command succeed? List each distinct error or failure with its file and line. Ignore progress noise.'
        tail = '\n'.join(output.strip().splitlines()[-4:])
        if len(output) < 600:
            out = f'exit {code}\n{output.strip()}'
        else:
            result = digest.answer(output, question, max_words, tool='digest_command')
            out = f'exit {code}\n{digest.render(result, "output")}\nLast lines:\n{tail}\nFull output: {full} ({len(output.splitlines())} lines)'
        store.write_job(job, {'id': job, 'kind': 'command', 'state': 'done', 'command': command, 'exit': code})
        return _saved('digest_command', len(output), out)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def digest_many(root: str, glob: str, question: str, max_files: int = 25, max_words_each: int = 40) -> str:
    """Ask the same question of many files (for example every *.md under a folder).

    Returns one short answer per file with a checked quote. Use it for surveys such as
    "which of these documents still mention the old part" or "what does each module export"."""
    try:
        base = Path(root).expanduser().resolve()
        files = sandbox.walk(base, glob, max_files + 1)
        cut = len(files) > max_files
        lines, total = [], 0
        for rel in files[:max_files]:
            try:
                text = sandbox.read_text(base / rel, 400_000)
            except Exception as exc:
                lines.append(f'{rel}: (unreadable: {exc})')
                continue
            total += len(text)
            result = digest.answer(text, question, max_words_each, tool='digest_many')
            ev = result['evidence'][0] if result['evidence'] else None
            flag = ' [UNVERIFIED]' if result['rejected'] and not result['evidence'] else ''
            lines.append(f'{rel}: {result["answer"]}{flag}' + (f'  ({rel}:{ev["line"]} "{ev["quote"][:70]}")' if ev else ''))
        if cut:
            lines.append(f'[only the first {max_files} files were read]')
        return _saved('digest_many', total, '\n'.join(lines) or 'no file matches')
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def extract_from_file(path: str, json_schema: str, instructions: str, grep: str = '') -> str:
    """Structured data from a file, in the JSON schema you give (as a string).

    Example: a pin table from a datasheet, the failing tests from a log, the parts of a BOM.
    Values the file does not give come back as null. grep narrows a large file first."""
    try:
        text = sandbox.read_text(Path(path).expanduser())
        data, tokens, parts = digest.extract(text, json.loads(json_schema), instructions, grep)
        return _saved('extract', len(text), json.dumps(data, separators=(',', ':')), executor_tokens=tokens)
    except Exception as exc:
        return _fail(exc)


# delegated work --------------------------------------------------------------------------------
def _receipt(job):
    data = store.read_job(job)
    if not data:
        return f'unknown job {job}'
    if data['state'] == 'running':
        last = ''
        log = store.JOBS / job / 'log.json'
        if log.exists():
            entries = json.loads(log.read_text())
            last = f', last tool: {entries[-1]["tool"]}' if entries else ''
        return f'job {job}: running, step {data.get("steps", 0)}{last}. Call job_status again.'
    lines = [f'job {job}: {data["state"].upper()}  ({data.get("steps", 0)} steps, {data.get("repairs", 0)} repairs, '
             f'{data.get("seconds", 0)} s, {data.get("tokens", 0)} executor tokens)']
    if data.get('summary'):
        lines.append(f'executor: {data["summary"]}')
    for rel, kind, add, rem in data.get('changes', []):
        lines.append(f'  {kind:7} {rel}  +{add} -{rem}')
    if not data.get('changes'):
        lines.append('  no file changed')
    for c in data.get('checks', []):
        lines.append(f'  check {"PASS" if c["exit"] == 0 else "FAIL"}  $ {c["command"]}')
        if c['exit'] != 0:
            lines.append('    ' + c['tail'][-500:].replace('\n', '\n    '))
    hint = {'verified': 'Checks passed. Read job_diff if the change is delicate, then job_feedback.',
            'unverified': 'No check was given: read job_diff before you rely on it.',
            'checks_failed': 'Checks still fail. job_diff to see the attempt, job_rollback to undo it.',
            'blocked': 'The executor could not do it. Do it yourself or give more context.',
            'out_of_steps': 'Step limit reached. job_diff shows the partial work; job_rollback undoes it.',
            'error': 'The run broke. job_rollback undoes any partial change.'}.get(data['state'], '')
    return '\n'.join(lines + ([hint] if hint else []))


def _wait(job, seconds):
    entry = agent.RUNNING.get(job)
    if entry:
        entry[0].join(max(0.0, min(float(seconds), 1500.0)))


@mcp.tool()
def delegate(goal: str, workspace: str, verify_commands: list[str] = [], write_globs: list[str] = [],
             allow_run: list[str] = [], context: str = '', max_steps: int = 30, max_repairs: int = 2,
             wait_seconds: int = 240, model: str = '') -> str:
    """Give the local executor a bounded task in a project and get a receipt.

    goal: what to do, precise and self-contained (files, names, expected behaviour).
    workspace: absolute path of the project folder; the executor cannot leave it.
    verify_commands: shell commands that must exit 0 for the work to be accepted (tests, build,
      a grep that must find or not find something). They run after the executor finishes; their
      failures go back to it for up to max_repairs attempts. Give at least one whenever you can.
    write_globs: files it may write, as globs relative to the workspace (empty: any file).
    allow_run: regular expressions of commands the executor itself may run (empty: none).
    context: facts it needs and cannot find in the files.
    wait_seconds: how long this call waits; a longer task keeps running, poll it with job_status.

    Every file the executor changes is journalled: job_diff shows the change, job_rollback undoes it.
    Good tasks: mechanical edits across files, a function plus its test, docs brought in line
    with a change, renames. Poor tasks: design choices, anything without a check."""
    try:
        ws = sandbox.Workspace(workspace, write_globs, allow_run)
        job = agent.start(goal, ws, list(verify_commands), max(3, min(max_steps, 80)), max(0, min(max_repairs, 5)), model, context)
        _wait(job, wait_seconds)
        text = _receipt(job)
        store.log('delegate', kind='result', bytes_in=0, bytes_out=len(text), state=None)
        return text
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def job_status(job_id: str, wait_seconds: int = 120) -> str:
    """Receipt of a delegated job, waiting up to wait_seconds if it is still running."""
    _wait(job_id, wait_seconds)
    return _receipt(job_id)


@mcp.tool()
def job_diff(job_id: str, path: str = '', max_lines: int = 200) -> str:
    """Unified diff of what a delegated job changed (one file if path is given)."""
    entry = agent.RUNNING.get(job_id)
    if entry:
        text = entry[1].diff(path)
    else:
        saved = store.JOBS / job_id / 'changes.diff'
        if not saved.exists():
            return f'no diff for job {job_id}'
        text = saved.read_text()
        if path:
            blocks = ('\n' + text).split('\n--- ')
            text = '\n'.join('--- ' + b for b in blocks[1:] if b.splitlines()[1].endswith('b/' + path))
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'[{len(lines) - max_lines} more lines: ask for one path or raise max_lines]']
    out = '\n'.join(lines) or 'no change'
    store.log('job_diff', kind='result', bytes_in=0, bytes_out=len(out))
    return out


@mcp.tool()
def job_rollback(job_id: str) -> str:
    """Undo a delegated job: every file it changed goes back to its content before the job."""
    entry = agent.RUNNING.get(job_id)
    if entry and entry[0].is_alive():
        return 'the job is still running'
    return agent.rollback(job_id)


@mcp.tool()
def job_feedback(job_id: str, accepted: bool, lesson: str = '') -> str:
    """Your verdict on a delegated job. It feeds the acceptance statistics, and `lesson` (one
    sentence on what to do differently, or what was right) is given to the executor at its
    next tasks in the same project. This is how the executor improves under your review."""
    data = store.read_job(job_id)
    if not data:
        return f'unknown job {job_id}'
    data['accepted'] = bool(accepted)
    store.write_job(job_id, data)
    store.log('feedback', kind='feedback', job=job_id, accepted=bool(accepted), state=data.get('state'))
    if lesson.strip():
        store.add_lesson(store.scope_of(data.get('workspace', '.')), lesson, 'review of ' + job_id)
    return 'recorded' + (' with a lesson' if lesson.strip() else '')


# memory and accounting -------------------------------------------------------------------------
@mcp.tool()
def lesson_add(project_path: str, text: str) -> str:
    """Teach the executor a standing rule for a project (or for every project with project_path '*').
    Example: 'Comments in English, no em dashes.' The executor reads its lessons before each task."""
    scope = '*' if project_path.strip() == '*' else store.scope_of(project_path)
    store.add_lesson(scope, text)
    return f'lesson stored for {scope}'


@mcp.tool()
def lessons(project_path: str, remove_containing: str = '') -> str:
    """Lessons the executor has for a project. remove_containing deletes those with that text."""
    scope = '*' if project_path.strip() == '*' else store.scope_of(project_path)
    if remove_containing.strip():
        return f'removed {store.drop_lesson(scope, remove_containing)} lesson(s)'
    rows = store.lessons(scope, 50)
    return '\n'.join(f'- [{r["scope"]}] {r["text"]}' for r in rows) or 'no lesson yet'


@mcp.tool()
def ledger_report(days: float = 30.0) -> str:
    """What the local executor did and what it saved: calls and executor tokens per tool, the
    characters it read against the characters returned to you (with a token estimate), the
    acceptance rate of delegated jobs and its speed. Use it to decide what is worth delegating."""
    rows = store.ledger(days)
    if not rows:
        return 'no activity recorded'
    tools = {}
    for r in rows:
        t = tools.setdefault(r['tool'], {'llm': 0, 'pt': 0, 'ct': 0, 's': 0.0, 'calls': 0, 'in': 0, 'out': 0})
        if r.get('kind') == 'llm':
            t['llm'] += 1
            t['pt'] += r.get('prompt_tokens', 0)
            t['ct'] += r.get('completion_tokens', 0)
            t['s'] += r.get('seconds', 0)
        elif r.get('kind') == 'result':
            t['calls'] += 1
            t['in'] += r.get('bytes_in', 0)
            t['out'] += r.get('bytes_out', 0)
    lines = [f'Last {days:g} days', 'tool              calls  executor tokens (in/out)   read chars -> returned chars   est. orchestrator tokens saved']
    total = 0
    for name, t in sorted(tools.items()):
        if name == 'feedback':
            continue
        saved = max(0, round((t['in'] - t['out']) / store.CHARS_PER_TOKEN))
        total += saved
        lines.append(f'{name:17} {t["calls"]:5}  {t["pt"]:>9}/{t["ct"]:<9}        {t["in"]:>9} -> {t["out"]:<9}        {saved}')
    lines.append(f'Estimated orchestrator input tokens saved: {total} (material the executor read for you, minus what it returned)')
    speed = [(r.get('completion_tokens', 0), r.get('seconds', 0)) for r in rows if r.get('kind') == 'llm' and r.get('seconds', 0) > 1]
    if speed:
        lines.append(f'Executor speed: {sum(a for a, _ in speed) / sum(b for _, b in speed):.0f} tokens/s over {len(speed)} calls')
    jobs = [r for r in rows if r['tool'] == 'delegate' and r.get('kind') == 'result' and r.get('state')]
    if jobs:
        states = {}
        for r in jobs:
            states[r.get('state')] = states.get(r.get('state'), 0) + 1
        lines.append('Delegated jobs: ' + ', '.join(f'{k} {v}' for k, v in sorted(states.items())))
    verdicts = [r for r in rows if r.get('kind') == 'feedback']
    if verdicts:
        ok = sum(1 for r in verdicts if r.get('accepted'))
        lines.append(f'Reviewed by the orchestrator: {ok} accepted of {len(verdicts)} ({100 * ok // len(verdicts)} %)')
    return '\n'.join(lines)


if __name__ == '__main__':
    store.init()
    mcp.run()
