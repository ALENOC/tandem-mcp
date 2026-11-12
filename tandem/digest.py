"""Reading on behalf of the orchestrator: answers with evidence that is checked against the source."""
import json
import re

from . import engine, sandbox

CHUNK_CHARS = 36000
ANSWER = {'type': 'object', 'required': ['answer', 'evidence'], 'properties': {
    'answer': {'type': 'string'},
    'evidence': {'type': 'array', 'items': {'type': 'object', 'required': ['line', 'quote'], 'properties': {
        'line': {'type': 'integer'}, 'quote': {'type': 'string'}}}}}}
NOTES = {'type': 'object', 'required': ['relevant', 'notes'], 'properties': {
    'relevant': {'type': 'boolean'},
    'notes': {'type': 'array', 'items': {'type': 'object', 'required': ['line', 'quote', 'fact'], 'properties': {
        'line': {'type': 'integer'}, 'quote': {'type': 'string'}, 'fact': {'type': 'string'}}}}}}
SYSTEM = ('You read material for a senior engineer who will not see it. Answer only from the material. '
          'Every claim needs evidence: the line number shown at the start of a line and a short exact quote '
          'copied from that line. If the material does not answer, say so. No preamble, no advice.')


def numbered(text, first=1):
    return '\n'.join(f'{n}| {line}' for n, line in enumerate(text.splitlines(), first))


def prefilter(text, pattern, context=3):
    """Keep only the lines that match a regular expression, with context, original numbers kept."""
    lines = text.splitlines()
    rx = re.compile(pattern, re.I)
    keep = set()
    for i, line in enumerate(lines):
        if rx.search(line):
            keep.update(range(max(0, i - context), min(len(lines), i + context + 1)))
    out, last = [], None
    for i in sorted(keep):
        if last is not None and i != last + 1:
            out.append('...')
        out.append(f'{i + 1}| {lines[i]}')
        last = i
    return '\n'.join(out), len(keep)


def chunks(body):
    """Split numbered text on line ends into pieces of about CHUNK_CHARS."""
    out, cur, size = [], [], 0
    for line in body.splitlines():
        if size + len(line) > CHUNK_CHARS and cur:
            out.append('\n'.join(cur))
            cur, size = [], 0
        cur.append(line[:2000])
        size += len(line) + 1
    if cur:
        out.append('\n'.join(cur))
    return out


def squash(s):
    return re.sub(r'\s+', ' ', s).strip().lower()


def check_evidence(evidence, lines):
    """An evidence item stands only if its quote really is at that line (two lines of slack)."""
    good, bad = [], 0
    for item in evidence:
        quote = squash(str(item.get('quote', '')))
        n = item.get('line', 0)
        if not isinstance(n, int) or len(quote) < 3:
            bad += 1
            continue
        near = [i + 1 for i in range(max(0, n - 3), min(len(lines), n + 2)) if quote in squash(lines[i])]
        if near:                                         # the exact line, when the number is off by one or two
            good.append({'line': min(near, key=lambda i: abs(i - n)), 'quote': str(item['quote']).strip()[:160]})
        elif quote in squash(' '.join(lines[max(0, n - 3):n + 2])):      # a quote that spans lines
            good.append({'line': n, 'quote': str(item['quote']).strip()[:160]})
        else:
            found = next((i + 1 for i, line in enumerate(lines) if quote in squash(line)), None)
            if found:                                    # right quote, wrong line number: corrected
                good.append({'line': found, 'quote': str(item['quote']).strip()[:160]})
            else:
                bad += 1
    return good, bad


def answer(text, question, max_words=120, grep='', tool='digest', model=''):
    """Answer a question about a text. Returns a dict with the answer, the verified evidence,
    the number of evidence items that failed the check, and the executor token use."""
    lines = text.splitlines()
    body = numbered(text)
    if grep:
        body, hits = prefilter(text, grep)
        if not hits:
            return {'answer': f'No line matches /{grep}/.', 'evidence': [], 'rejected': 0, 'chunks': 0, 'tokens': 0}
    parts = chunks(body)
    tokens = 0
    if len(parts) > 1:                                   # map: notes per chunk, reduce: answer from the notes
        notes = []
        for k, part in enumerate(parts):
            data, used = engine.chat_json(
                [{'role': 'system', 'content': SYSTEM},
                 {'role': 'user', 'content': f'Question: {question}\n\nPart {k + 1} of {len(parts)} of the material:\n{part}\n\n'
                                             'List the facts of this part that help to answer, each with its line and exact quote. '
                                             'Set relevant to false and notes to [] if this part has none.'}],
                NOTES, tool=tool, model=model, max_tokens=1500)
            tokens += used['prompt'] + used['completion']
            if data.get('relevant'):
                notes += data.get('notes', [])[:25]
        if not notes:
            return {'answer': 'The material does not answer the question.', 'evidence': [], 'rejected': 0,
                    'chunks': len(parts), 'tokens': tokens}
        kept, _ = check_evidence(notes, lines)
        facts = {(n['line'], squash(n['quote'])): n for n in notes}
        material = '\n'.join(f'{e["line"]}| {e["quote"]}  -- {facts.get((e["line"], squash(e["quote"])), {}).get("fact", "")}'
                             for e in kept)
        prompt = f'Question: {question}\n\nVerified extracts of the material (line| quote -- fact):\n{material}'
    else:
        prompt = f'Question: {question}\n\nMaterial:\n{parts[0] if parts else ""}'
    data, used = engine.chat_json(
        [{'role': 'system', 'content': SYSTEM},
         {'role': 'user', 'content': prompt + f'\n\nAnswer in at most {max_words} words, then give the evidence.'}],
        ANSWER, tool=tool, model=model, max_tokens=max(600, max_words * 6))
    tokens += used['prompt'] + used['completion']
    good, bad = check_evidence(data.get('evidence', []), lines)
    return {'answer': str(data.get('answer', '')).strip(), 'evidence': good, 'rejected': bad, 'chunks': len(parts), 'tokens': tokens}


def render(result, source=''):
    """Compact text for the orchestrator."""
    out = [result['answer']]
    if result['evidence']:
        out.append('Evidence (checked against the source):')
        out += [f'  {source}:{e["line"]}  "{e["quote"]}"' for e in result['evidence'][:12]]
    if result['rejected']:
        out.append(f'WARNING: {result["rejected"]} evidence item(s) were not found in the source and were dropped. '
                   'Treat the related claims as unverified.')
    if not result['evidence'] and not result['rejected']:
        out.append('(no evidence given)')
    return '\n'.join(out)


def extract(text, schema, instructions, grep='', tool='extract', model=''):
    """Structured data from a text, in the given JSON schema."""
    body = numbered(text)
    if grep:
        body, _ = prefilter(text, grep, context=1)
    parts = chunks(body)
    if len(parts) > 6:
        raise engine.ExecutorError('material too large for one extraction: narrow it with grep')
    results, tokens = [], 0
    for part in parts:
        data, used = engine.chat_json(
            [{'role': 'system', 'content': 'You extract data exactly as written in the material. Never guess a value: '
                                           'use null or leave it out when the material does not give it.'},
             {'role': 'user', 'content': f'{instructions}\n\nMaterial (line| text):\n{part}'}],
            schema, tool=tool, model=model, max_tokens=4000)
        tokens += used['prompt'] + used['completion']
        results.append(data)
    return (results[0] if len(results) == 1 else results), tokens, len(parts)


def agreement(answers):
    """Share of the answers equal to the most common one, after normalisation."""
    keys = [json.dumps(a, sort_keys=True) if not isinstance(a, str) else squash(a) for a in answers]
    best = max(set(keys), key=keys.count)
    return keys.count(best) / len(keys), answers[keys.index(best)]
