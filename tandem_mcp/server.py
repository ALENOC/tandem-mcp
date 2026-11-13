"""Tandem MCP server: a cloud orchestrator model and a local executor model.

The orchestrator keeps the decisions and the final check; the local model does the reading and
the mechanical work on the machine and reports in a few lines. The local model can be any model
behind an OpenAI compatible server (LM Studio, Ollama, llama.cpp, vLLM and others). Four ideas
shape the tools:

1. Contracts. `delegate` gives the executor a workspace, write and command limits and the checks
   that decide acceptance. The server runs the checks itself and returns a receipt.
2. Checked evidence. `digest_*` answers come with quotes that the server looks up in the source;
   a quote that is not there is dropped and reported, so a made-up answer is visible.
3. Supervised memory. The verdict of the orchestrator on a job becomes a lesson that the executor
   reads at its next task in that project, and the ledger shows where delegation pays.
4. Any model. The server measures what the model can do and adapts the protocol to it.
"""
import json
import logging
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import __version__, agent, digest, engine, sandbox, store

GUIDE = '''Hybrid orchestration (cloud model = architect & reviewer, local model = reader & bounded executor, free to use):
- Reading & extraction: use digest_file (with grep when possible), digest_command, digest_many, and extract_from_file
  instead of reading large files/logs into cloud context. Quotes and numbers are checked against the source;
  if a result is flagged unsupported/contested or ask(samples>1) shows agreement < 1.0, inspect only the cited lines.
- Bounded coding: use delegate with tight write_globs and real verify_commands (tests, build, lint, syntax).
  For multi-file or >150-line features, split into small modular tasks via delegate_many (with `after` dependencies)
  rather than asking a small local model for one giant single-shot file.
- Keep frontier quality: verify_commands prove code runs/parses, not design or visual polish. Review job_diff
  (or rendered output for UI) on non-trivial changes; use job_continue(hint=...) for targeted fixes, job_rollback
  to undo cleanly, and job_feedback / lesson_add so mistakes become standing project rules.
- Skip delegation for trivial 1-line edits or purely open-ended design with no check.
The executor is slow. If a call runs past the client timeout and moves to the background, do not cancel it
or redo its work with the cloud model on your own: ask the user whether to keep waiting or to stop it.'''
mcp = MCPServer('tandem', version=__version__, instructions=GUIDE)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)


def _fail(exc):
    return f'ERROR: {exc}'


def _saved(tool, bytes_in, text, **more):
    store.log(tool, kind='result', bytes_in=bytes_in, bytes_out=len(text), **more)
    return text


def _caps_line(found):
    return (f'tool calls: {"native" if found["tools"] else "JSON replies (no native tool calling)"}, '
            f'JSON schema: {"forced by the server" if found["schema"] else "by prompt and repair"}, '
            f'reasoning text: {"yes, stripped" if found["thinking"] else "no"}'
            + (f', {found["tps"]} tokens/s' if found.get('tps') else ''))


# status ----------------------------------------------------------------------------------------
@mcp.tool()
def executor_status() -> str:
    """State of the local executor: server, models, which one is in use, its context length,
    what it can do (when it has been probed) and how its commands are confined."""
    try:
        server = engine.connect(refresh=True)
        rows = engine.models(refresh=True)
        active = engine.default_model()
    except Exception as exc:
        return f'No local model server: {exc}'
    lines = [f'{server["name"]} online at {server["url"]}', f'executor model: {active}  (context {engine.context_tokens(active)})']
    known = store.model_caps(f'{server["url"]}|{active}')
    lines.append('  ' + (_caps_line(known) if known and known.get('probed') else 'not probed yet: executor_probe measures what it can do'))
    state = {True: 'loaded', False: 'not loaded', None: ''}
    lines += [f'- {m["id"]}  {state[m["loaded"]]}  {m["type"]}  context {m["context"] or "unknown"}' for m in rows]
    others = [f'{name} ({url})' for name, url in engine.servers() if url != server['url']]
    if others:
        lines.append('other servers that answer (TANDEM_BASE_URL selects one): ' + ', '.join(others))
    lines.append('commands of the executor: ' + sandbox.describe_jail())
    if engine.context_tokens(active) < 8000:
        lines.append('NOTE: a context under 8000 tokens is enough for digest and ask, tight for delegate.')
    return '\n'.join(lines)


@mcp.tool()
def executor_probe(model: str = '', force: bool = False) -> str:
    """Measure what a local model can do on this server: native tool calls, JSON schema forced
    by the server, reasoning text, speed. The result is stored and the tools adapt to it: a model
    without tool calling still does `delegate` through JSON replies. Runs by itself at the first
    use of a model; force repeats it (after a change of server settings or of chat template)."""
    try:
        name = model or engine.default_model()
        found = engine.probe(name, force)
        notes = ''.join(f'\n  note: {n}' for n in found.get('notes', []))
        return f'{name} on {engine.connect()["name"]}: {_caps_line(found)}{notes}'
    except Exception as exc:
        return _fail(exc)


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
                reply, _ = engine.chat(messages, tool='ask', model=model, max_tokens=max_tokens, temperature=temperature)
                answers.append(reply.content)
        if len(answers) == 1:
            text = answers[0] if isinstance(answers[0], str) else json.dumps(answers[0], indent=1)
            return _saved('ask', 0, text)
        share, best = digest.agreement(answers)
        text = best if isinstance(best, str) else json.dumps(best, indent=1)
        return _saved('ask', 0, f'[agreement {share:.2f} over {len(answers)} runs]\n{text}', agreement=share)
    except Exception as exc:
        return _fail(exc)


# reading for the orchestrator ------------------------------------------------------------------
def _evidence(result):
    return {'model': result.get('model', ''), 'quotes_ok': len(result['evidence']),
            'quotes_bad': result['rejected'] + result.get('notes_dropped', 0), 'cached': bool(result.get('cached'))}


@mcp.tool()
def digest_file(path: str, question: str, max_words: int = 120, grep: str = '', model: str = '') -> str:
    """Ask a question about a file (text, source, log, JSON, PDF) instead of reading it.

    The executor reads the whole file, in parts sized to its context, and answers in at most
    max_words with line references and quotes. The server checks every quote against the file
    and lists the numbers of the answer that are not in the file.
    grep: optional regular expression; only matching lines (with context) are read, which is
    faster on large files when you know what to look for."""
    try:
        text = sandbox.read_text(Path(path).expanduser())
        result = digest.answer(text, question, max_words, grep, tool='digest_file', model=model)
        out = digest.render(result, Path(path).name)
        return _saved('digest_file', len(text), out, executor_tokens=result['tokens'], **_evidence(result))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def digest_command(command: str, cwd: str, question: str = '', max_words: int = 120, timeout: int = 600) -> str:
    """Run a command of yours (build, tests, linter, DRC) and get the verdict instead of the output.

    Returns the exit code, the answer of the executor to `question` (default: did it succeed,
    and what are the errors) with checked quotes, the last lines of the output, and the path
    of the full output in case you need to read a part yourself. The command runs as you wrote
    it, with your rights: the limits apply only to commands the executor chooses."""
    try:
        job, folder = store.new_job('command')
        code, output = sandbox.run(command, Path(cwd).expanduser(), timeout)
        full = folder / 'output.txt'
        full.write_text(output)
        question = question or 'Did the command succeed? List each distinct error or failure with its file and line. Ignore progress noise.'
        tail = '\n'.join(output.strip().splitlines()[-4:])
        more = {}
        if len(output) < 600:
            out = f'exit {code}\n{output.strip()}'
        else:
            result = digest.answer(output, question, max_words, tool='digest_command', cache=False)
            more = _evidence(result)
            out = f'exit {code}\n{digest.render(result, "output")}\nLast lines:\n{tail}\nFull output: {full} ({len(output.splitlines())} lines)'
        store.write_job(job, {'id': job, 'kind': 'command', 'state': 'done', 'command': command, 'exit': code})
        return _saved('digest_command', len(output), out, **more)
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
        lines, total, good, bad = [], 0, 0, 0
        for rel in files[:max_files]:
            try:
                text = sandbox.read_text(base / rel, 400_000)
                result = digest.answer(text, question, max_words_each, tool='digest_many')
            except Exception as exc:
                lines.append(f'{rel}: (not read: {str(exc)[:120]})')
                continue
            total += len(text)
            good += len(result['evidence'])
            bad += result['rejected']
            ev = result['evidence'][0] if result['evidence'] else None
            flag = ' [UNVERIFIED]' if result['rejected'] and not result['evidence'] else ''
            lines.append(f'{rel}: {result["answer"]}{flag}' + (f'  ({rel}:{ev["line"]} "{ev["quote"][:70]}")' if ev else ''))
        if cut:
            lines.append(f'[only the first {max_files} files were read]')
        return _saved('digest_many', total, '\n'.join(lines) or 'no file matches', quotes_ok=good, quotes_bad=bad)
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def extract_from_file(path: str, json_schema: str, instructions: str, grep: str = '') -> str:
    """Structured data from a file, in the JSON schema you give (as a string).

    Example: a pin table from a datasheet, the failing tests from a log, the parts of a BOM.
    Values the file does not give come back as null. grep narrows a large file first.
    Every extracted string and number is looked up in the file: those that are not there
    are listed after the data, so an invented value is visible."""
    try:
        text = sandbox.read_text(Path(path).expanduser())
        data, tokens, parts = digest.extract(text, json.loads(json_schema), instructions, grep)
        loose = digest.loose_values(data, text)
        out = json.dumps(data, separators=(',', ':'))
        if loose:
            out += '\nNOTE: not found in the file as written (reworded, computed or made up): ' + \
                   ', '.join(json.dumps(v)[:60] for v in loose[:12]) + (f' and {len(loose) - 12} more' if len(loose) > 12 else '')
        return _saved('extract', len(text), out, executor_tokens=tokens, values_loose=len(loose))
    except Exception as exc:
        return _fail(exc)


# delegated work --------------------------------------------------------------------------------
HINTS = {'verified': 'Checks passed. Read job_diff if the change is delicate, then job_feedback.',
         'unverified': 'No check was given: read job_diff before you rely on it.',
         'checks_failed': 'Not accepted. job_diff shows the attempt; job_continue with a hint, or job_rollback.',
         'blocked': 'The executor could not do it. job_continue with what it lacks, or do it yourself.',
         'stuck': 'The executor went in circles. job_continue with a different approach, or job_rollback.',
         'out_of_steps': 'Step limit reached. job_continue gives more steps; job_rollback undoes the partial work.',
         'out_of_time': 'Time limit reached. job_continue gives more steps; job_rollback undoes the partial work.',
         'error': 'The run broke. job_rollback undoes any partial change.'}


def _batch_receipt(job, data):
    lines = [f'batch {job}: {data["state"].upper()}  ({len(data.get("tasks", []))} tasks, {data.get("seconds", 0)} s)']
    for row in data.get('tasks', []):
        sub = store.read_job(row['job']) if row.get('job') else None
        state = sub['state'] if sub else row['state']
        extra = row.get('why') or (sub.get('summary', '')[:110] if sub else '')
        lines.append(f'  {row["name"]}: {state.upper()}' + (f'  job {row["job"]}' if row.get('job') else '') + (f'  {extra}' if extra else ''))
    if data['state'] == 'running':
        lines.append('Call job_status again.')
    else:
        lines.append('job_status of a task job gives its receipt, job_diff its changes; job_rollback of the batch undoes every task.')
    return '\n'.join(lines)


def _receipt(job):
    data = store.read_job(job)
    if not data:
        return f'unknown job {job}'
    if data.get('kind') == 'batch':
        return _batch_receipt(job, data)
    if data['state'] == 'running':
        entries = store.read_json(store.JOBS / job / 'log.json', []) or []
        last = f', last tool: {entries[-1]["tool"]}' if entries else ''
        return f'job {job}: running, step {data.get("steps", 0)}{last}. Call job_status again.'
    lines = [f'job {job}: {data["state"].upper()}  ({data.get("steps", 0)} steps, {data.get("repairs", 0)} repairs, '
             f'{data.get("seconds", 0)} s, {data.get("tokens", 0)} executor tokens, {data.get("protocol", "")})']
    if data.get('summary'):
        lines.append(f'executor: {data["summary"]}')
    for rel, kind, add, rem in data.get('changes', []):
        lines.append(f'  {kind:7} {rel}  +{add} -{rem}')
    if not data.get('changes'):
        lines.append('  no file changed')
    syntax = data.get('syntax') or {}
    if syntax.get('bad'):
        lines += [f'  syntax ERROR {rel}: {why}' for rel, why in syntax['bad']]
    if syntax.get('ok') or syntax.get('unchecked'):
        lines.append('  syntax ok: ' + (', '.join(syntax.get('ok', [])) or 'none') +
                     (f'; no checker for: {", ".join(syntax["unchecked"])}' if syntax.get('unchecked') else ''))
    before = {c['command']: c['exit'] for c in data.get('before', [])}
    for c in data.get('checks', []):
        was = before.get(c['command'])
        note = '' if was is None else ('  (failed before the job)' if was != 0 else '  (already passed before the job)')
        lines.append(f'  check {"PASS" if c["exit"] == 0 else "FAIL"}  $ {c["command"]}{note}')
        if c['exit'] != 0:
            lines.append('    ' + c['tail'][-500:].replace('\n', '\n    '))
    if data.get('weak') and data['state'] == 'verified':
        lines.append('NOTE: every check already passed before the job, so the checks do not prove this work. Read job_diff.')
    elif data['state'] == 'verified' and data.get('changes'):
        churn = sum(add + rem for _, _, add, rem in data['changes'])
        if churn > 40:
            lines.append(f'NOTE: non-trivial change ({churn} lines changed). Inspect job_diff for quality/edge cases before accepting, '
                         'or use job_continue for targeted polish.')
    if data['state'] in ('stuck', 'out_of_steps') and not data.get('changes'):
        lines.append('HINT: no file was changed; if the task was too large for one shot, split it into smaller modules with delegate_many.')
    if data.get('restored'):
        lines.append('NOTE: the executor changed files of the checks through a command; they were put back: ' + ', '.join(data['restored']))
    if data.get('touched'):
        status = data.get('backup_status')
        unbacked = data.get('unbacked_files') or []
        if not status:
            has_snap = (store.JOBS / job / 'snapshot.json').exists()
            status = 'fully_backed' if has_snap else 'unbacked'
        if status == 'fully_backed':
            note = 'fully_backed, covered by workspace snapshot (job_rollback undoes them)'
        elif status == 'partially_backed':
            note = f'partially_backed (unbacked, not undone by rollback: {", ".join(unbacked[:12])})'
        else:
            note = 'unbacked (outside the journal, job_rollback does not undo them)'
        lines.append(f'NOTE: changed by commands, {note}: ' + ', '.join(data['touched'][:12]))
    if data['state'] not in ('verified', 'unverified', 'rolled_back') and data.get('tried'):
        lines.append('Last steps of the executor:')
        lines += ['  ' + t for t in data['tried']]
    hint = HINTS.get(data['state'], '')
    return '\n'.join(lines + ([hint] if hint else []))


def _wait(job, seconds):
    entry = agent.RUNNING.get(job)
    if entry:
        entry[0].join(max(0.0, min(float(seconds), 1500.0)))


@mcp.tool()
def delegate(goal: str, workspace: str, verify_commands: list[str] = [], write_globs: list[str] = [],
             allow_run: list[str] = [], immutable: list[str] = [], context: str = '', max_steps: int = 30,
             max_repairs: int = 2, wait_seconds: int = 240, model: str = '', baseline: bool = True,
             max_seconds: int = 0, checks_network: bool = False, unjailed_checks: bool = False) -> str:
    """Give the local executor a bounded task in a project and get a receipt.

    goal: what to do, precise and self-contained (files, names, expected behaviour).
    workspace: absolute path of the project folder; the executor cannot leave it.
    verify_commands: shell commands that must exit 0 for the work to be accepted (tests, build,
      a grep that must find or not find something). They run after the executor finishes in an
      isolated sandbox with secret env vars stripped; their failures go back to it for up to
      max_repairs attempts. Give at least one whenever you can. The files they name (and test
      folders) are read only for the executor unless write_globs names them.
    write_globs: files it may write, as globs relative to the workspace (empty: any file).
    allow_run: regular expressions of commands the executor itself may run (empty: none). Every
      part of a pipeline or chain must match one.
    immutable: files or globs relative to the workspace that are always read only.
    context: facts it needs and cannot find in the files.
    wait_seconds: how long this call waits; a longer task keeps running, poll it with job_status.
    baseline: run the checks once before the work. The executor starts from their failures, and
      the receipt says when a check already passed, which means it proves nothing about this work.
    max_seconds: time limit of the job (0: none).
    checks_network: allow network access inside the sandbox when running verify_commands.
    unjailed_checks: run verify_commands outside bubblewrap (for checks needing host resources).

    Every file the executor changes is journalled (and command changes are snapshotted): job_diff
    shows the change, job_rollback undoes it without overwriting later user edits.
    The syntax of every changed file is checked before the checks run.
    Good tasks: mechanical edits across files, a function plus its test, docs brought in line
    with a change, renames. Poor tasks: design choices, anything without a check."""
    try:
        ws = sandbox.Workspace(workspace, write_globs, allow_run, immutable)
        job = agent.start(goal, ws, list(verify_commands), max(3, min(max_steps, 80)), max(0, min(max_repairs, 5)), model,
                          context, baseline, max(0, int(max_seconds)),
                          checks_network=checks_network, unjailed_checks=unjailed_checks)
        _wait(job, wait_seconds)
        return _saved('delegate', 0, _receipt(job))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def delegate_many(tasks: list[dict], workspace: str, allow_run: list[str] = [], immutable: list[str] = [],
                  context: str = '', workers: int = 1, max_steps: int = 30, max_repairs: int = 2,
                  wait_seconds: int = 240, model: str = '', checks_network: bool = False,
                  unjailed_checks: bool = False) -> str:
    """Give the executor several tasks with an order, each one a contract of its own.

    tasks: a list of objects with
      name             short unique name
      goal             what to do, self-contained
      verify_commands  checks of this task (list of shell commands)
      write_globs      files this task may write (list of globs)
      after            names of the tasks that must succeed first (list)
      context          facts for this task (optional)
      immutable        read-only files or globs for this task (optional)
    workers: tasks run side by side, for a server with several request slots (default 1).

    A task starts when the tasks it comes after are verified. A task whose prerequisite failed
    is cancelled with the reason and not started. Two tasks that run at the same time cannot
    write the same file: the first to write it owns it until it ends. Each task has its own job,
    receipt, diff and rollback; job_rollback of the batch undoes all of them, newest first."""
    try:
        specs = []
        for n, t in enumerate(tasks):
            if not isinstance(t, dict) or not str(t.get('goal', '')).strip():
                return _fail(f'task {n + 1} has no goal')
            specs.append({'name': str(t.get('name') or f'task{n + 1}'), 'goal': str(t['goal']),
                          'verify_commands': list(t.get('verify_commands') or []), 'write_globs': list(t.get('write_globs') or []),
                          'immutable': list(t.get('immutable') or []),
                          'checks_network': bool(t.get('checks_network', checks_network)),
                          'unjailed_checks': bool(t.get('unjailed_checks', unjailed_checks)),
                          'after': [str(a) for a in (t.get('after') or [])], 'context': str(t.get('context') or '')})
        if not specs or len(specs) > 16:
            return _fail('a batch holds 1 to 16 tasks')
        job = agent.start_batch(specs, workspace, allow_run, max(1, min(int(workers), 8)), max(3, min(max_steps, 80)),
                                max(0, min(max_repairs, 5)), model, context,
                                checks_network=checks_network, unjailed_checks=unjailed_checks, immutable=immutable)
        _wait(job, wait_seconds)
        return _saved('delegate', 0, _receipt(job))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def job_status(job_id: str, wait_seconds: int = 120) -> str:
    """Receipt of a delegated job or batch, waiting up to wait_seconds if it is still running."""
    _wait(job_id, wait_seconds)
    return _saved('delegate', 0, _receipt(job_id))


@mcp.tool()
def job_continue(job_id: str, hint: str, extra_steps: int = 15, wait_seconds: int = 240) -> str:
    """Send a stopped job on with a hint of yours, in the same conversation of the executor.

    For a job that ended blocked, stuck, checks_failed, out_of_steps or out_of_time, or a
    finished one that needs a correction. The executor keeps what it read and tried, so one
    sentence from you (the cause it missed, the file to look at, the approach to take) costs far
    less than a new task. The journal goes on: job_rollback still undoes the whole job. It also
    works after a restart of the server, since the conversation is saved at every step."""
    try:
        if not hint.strip():
            return _fail('give a hint: what the executor missed or should do next')
        agent.resume(job_id, hint, max(3, min(int(extra_steps), 60)))
        _wait(job_id, wait_seconds)
        return _saved('delegate', len(hint), _receipt(job_id))
    except Exception as exc:
        return _fail(exc)


@mcp.tool()
def job_diff(job_id: str, path: str = '', max_lines: int = 200) -> str:
    """Unified diff of what a delegated job changed (one file if path is given)."""
    entry = agent.RUNNING.get(job_id)
    if entry and entry[1] is None:
        return 'this is a batch: ask for the diff of one of its task jobs (job_status lists them)'
    if entry and entry[0].is_alive():
        text = entry[1].diff(path)
    else:
        saved = store.JOBS / job_id / 'changes.diff'
        if not store.read_job(job_id) or not saved.exists():
            return f'no diff for job {job_id}'
        text = saved.read_text()
        if path:
            blocks = ('\n' + text).split('\n--- ')
            text = '\n'.join('--- ' + b for b in blocks[1:] if len(b.splitlines()) > 1 and b.splitlines()[1].endswith('b/' + path))
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f'[{len(lines) - max_lines} more lines: ask for one path or raise max_lines]']
    return _saved('job_diff', 0, '\n'.join(lines) or 'no change')


@mcp.tool()
def job_rollback(job_id: str) -> str:
    """Undo a delegated job: every file it changed goes back to its content before the job.
    For a batch, every task is undone, newest first."""
    entry = agent.RUNNING.get(job_id)
    if entry and entry[0].is_alive():
        return 'the job is still running'
    if not store.read_job(job_id):
        return f'unknown job {job_id}'
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
    store.log('feedback', kind='feedback', job=job_id, accepted=bool(accepted), state=data.get('state'),
              model=data.get('used') or data.get('model') or 'default')
    if lesson.strip():
        store.add_lesson(store.scope_of(data.get('workspace', '.')), lesson, 'review of ' + job_id)
    return 'recorded' + (' with a lesson' if lesson.strip() else '')


# memory and accounting -------------------------------------------------------------------------
@mcp.tool()
def lesson_add(project_path: str, text: str) -> str:
    """Teach the executor a standing rule for a project (or for every project with project_path '*').
    Example: 'Comments in English, no em dashes.' The executor reads its lessons before each task."""
    scope = '*' if project_path.strip() == '*' else store.scope_of(project_path)
    return f'lesson stored for {scope}' if store.add_lesson(scope, text) else f'{scope} already has this lesson'


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
    characters it read against the characters returned to you (with a token estimate), and per
    model the speed, the share of quotes that failed the check, the outcome of delegated jobs
    and your verdicts. Use it to decide what is worth delegating, and to which model."""
    rows = store.ledger(days)
    if not rows:
        return 'no activity recorded'
    tools, per_model = {}, {}
    for r in rows:
        kind = r.get('kind')
        t = tools.setdefault(r['tool'], {'pt': 0, 'ct': 0, 'calls': 0, 'in': 0, 'out': 0})
        m = per_model.setdefault(r.get('model') or 'default', {'ct': 0, 's': 0.0, 'ok': 0, 'bad': 0, 'jobs': {}, 'yes': 0, 'no': 0})
        if kind == 'llm':
            t['pt'] += r.get('prompt_tokens', 0)
            t['ct'] += r.get('completion_tokens', 0)
            if r.get('seconds', 0) > 1:
                m['ct'] += r.get('completion_tokens', 0)
                m['s'] += r.get('seconds', 0)
        elif kind == 'result':
            t['calls'] += 1
            t['in'] += r.get('bytes_in', 0)
            t['out'] += r.get('bytes_out', 0)
            m['ok'] += r.get('quotes_ok', 0)
            m['bad'] += r.get('quotes_bad', 0)
        elif kind == 'job':
            t['in'] += r.get('bytes_in', 0)
            m['jobs'][r.get('state')] = m['jobs'].get(r.get('state'), 0) + 1
        elif kind == 'feedback':
            m['yes' if r.get('accepted') else 'no'] += 1
    lines = [f'Last {days:g} days', 'tool              calls  executor tokens (in/out)   read chars -> returned chars   est. orchestrator tokens saved']
    total = 0
    for name, t in sorted(tools.items()):
        if name in ('feedback', 'probe'):
            continue
        saved = max(0, round((t['in'] - t['out']) / store.CHARS_PER_TOKEN))
        total += saved
        lines.append(f'{name:17} {t["calls"]:5}  {t["pt"]:>9}/{t["ct"]:<9}        {t["in"]:>9} -> {t["out"]:<9}        {saved}')
    lines.append(f'Estimated orchestrator input tokens saved: {total} (material the executor read for you, minus what it returned)')
    for name, m in sorted(per_model.items()):
        parts = []
        if m['s']:
            parts.append(f'{m["ct"] / m["s"]:.0f} tokens/s')
        if m['ok'] + m['bad']:
            parts.append(f'quotes dropped {m["bad"]} of {m["ok"] + m["bad"]} ({100 * m["bad"] // (m["ok"] + m["bad"])} %)')
        if m['jobs']:
            parts.append('jobs: ' + ', '.join(f'{k} {v}' for k, v in sorted(m['jobs'].items(), key=str)))
        if m['yes'] + m['no']:
            parts.append(f'accepted by you {m["yes"]} of {m["yes"] + m["no"]}')
        if parts:
            lines.append(f'{name}: ' + '; '.join(parts))
    return '\n'.join(lines)


def main():
    store.init()
    mcp.run()


if __name__ == '__main__':
    main()
