"""Client of the local model: any OpenAI compatible server, found by itself, with a probe of
what each model can do and accounting of every call.

Local models differ in three ways that matter here: whether they call tools natively, whether
the server can force a JSON schema on the output, and whether they print their reasoning. The
probe measures the three once per model and the rest of the server adapts, so the same tools
work with a large tool calling model and with a small one that only writes text."""
import json
import os
import re
import time
import urllib.error
import urllib.request

from openai import OpenAI

from . import store

KNOWN = [('LM Studio', 'http://127.0.0.1:1234/v1'), ('Ollama', 'http://127.0.0.1:11434/v1'),
         ('llama.cpp', 'http://127.0.0.1:8080/v1'), ('vLLM', 'http://127.0.0.1:8000/v1'),
         ('Jan', 'http://127.0.0.1:1337/v1'), ('KoboldCpp', 'http://127.0.0.1:5001/v1'),
         ('text-generation-webui', 'http://127.0.0.1:5000/v1'), ('LocalAI', 'http://127.0.0.1:8081/v1')]
DEFAULT_CONTEXT = {'ollama': 4096}
THINK = re.compile(r'<(think|thinking|reasoning|thought)>.*?</\1>', re.S | re.I)
THINK_END = re.compile(r'</(think|thinking|reasoning|thought)>', re.I)
THINK_OPEN = re.compile(r'\s*<(think|thinking|reasoning|thought)>', re.I)
_state = {'url': None, 'kind': None, 'name': None, 'client': None, 'models': None, 'models_at': 0.0, 'pinned': ''}


class ExecutorError(RuntimeError):
    pass


class Reply:
    """What one completion gave: the text without the reasoning, and the tool calls."""

    def __init__(self, content, calls, finish, thought):
        self.content, self.calls, self.finish, self.thought = content, calls, finish, thought


# where the model is ----------------------------------------------------------------------------
def _get(url, timeout=4.0, body=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + _key()})
    with urllib.request.urlopen(request, timeout=timeout) as r:
        return json.load(r)


def _key():
    return os.environ.get('TANDEM_API_KEY') or os.environ.get('LM_STUDIO_API_KEY') or 'local'


def _root(url):
    return re.sub(r'/v1/?$', '', url.rstrip('/'))


def _answers(url):
    try:
        return isinstance(_get(url.rstrip('/') + '/models', 1.5).get('data'), list)
    except Exception:
        return False


def _kind(url):
    root = _root(url)
    for kind, path, key in (('lmstudio', '/api/v0/models', 'data'), ('ollama', '/api/tags', 'models'),
                            ('llamacpp', '/props', 'default_generation_settings')):
        try:
            if key in _get(root + path, 1.5):
                return kind
        except Exception:
            continue
    return 'openai'


def connect(refresh=False, url=''):
    """The server in use. With no address in the environment the usual local ports are tried."""
    if _state['url'] and not refresh and not url:
        return _state
    if url:
        _state['pinned'] = url                           # an address given by the caller stays until another is given
    forced = _state['pinned'] or os.environ.get('TANDEM_BASE_URL') or os.environ.get('LM_STUDIO_BASE_URL')
    name = 'configured server'
    if forced:
        found = forced.rstrip('/')
    else:
        found = None
        for name, candidate in KNOWN:
            if _answers(candidate):
                found = candidate
                break
        if not found:
            raise ExecutorError('no local model server answers (tried ' + ', '.join(n for n, _ in KNOWN) +
                                '). Start one or set TANDEM_BASE_URL.')
    kind = _kind(found)
    label = {'lmstudio': 'LM Studio', 'ollama': 'Ollama', 'llamacpp': 'llama.cpp'}.get(kind, name)
    _state.update(url=found, kind=kind, name=label, models=None, models_at=0.0,
                  client=OpenAI(base_url=found, api_key=_key(), timeout=float(os.environ.get('TANDEM_TIMEOUT', 900)), max_retries=1))
    return _state


def servers():
    """Every known local server that answers now, for the status report."""
    return [(name, url) for name, url in KNOWN if _answers(url)]


def models(refresh=False):
    """Models of the server: id, loaded or not, context length, kind (chat or embeddings)."""
    s = connect()
    if s['models'] is not None and not refresh and time.time() - s['models_at'] < 15:
        return s['models']
    root, rows = _root(s['url']), None
    try:
        if s['kind'] == 'lmstudio':
            rows = [{'id': m['id'], 'loaded': m.get('state') == 'loaded', 'type': m.get('type') or 'llm',
                     'context': m.get('loaded_context_length') or m.get('max_context_length')}
                    for m in _get(root + '/api/v0/models')['data']]
        elif s['kind'] == 'ollama':
            running = {m.get('name'): m.get('context_length') for m in _get(root + '/api/ps').get('models', [])}
            rows = [{'id': m['name'], 'loaded': m['name'] in running, 'type': 'llm', 'context': running.get(m['name'])}
                    for m in _get(root + '/api/tags').get('models', [])]
        elif s['kind'] == 'llamacpp':
            ctx = (_get(root + '/props').get('default_generation_settings') or {}).get('n_ctx')
            rows = [{'id': m['id'], 'loaded': True, 'type': 'llm', 'context': ctx} for m in _get(s['url'] + '/models')['data']]
    except Exception:
        rows = None
    if rows is None:
        try:
            rows = [{'id': m['id'], 'loaded': None, 'type': 'llm', 'context': m.get('max_model_len') or m.get('context_length')}
                    for m in _get(s['url'] + '/models')['data']]
        except Exception as exc:
            raise ExecutorError(f'the model server at {s["url"]} does not answer: {exc}') from exc
    for m in rows:
        if 'embed' in m['id'].lower() or m['type'] in ('embeddings', 'embedding'):
            m['type'] = 'embeddings'
    s['models'], s['models_at'] = rows, time.time()
    return rows


def default_model():
    """TANDEM_MODEL, else the loaded chat model (no load delay), else the first chat model."""
    forced = os.environ.get('TANDEM_MODEL')
    if forced:
        return forced
    chat_models = [m for m in models() if m['type'] != 'embeddings']
    for m in chat_models:
        if m['loaded']:
            return m['id']
    if chat_models:
        return chat_models[0]['id']
    raise ExecutorError(f'no chat model on the server at {connect()["url"]}')


def context_tokens(model=''):
    """Context length of the model: TANDEM_CONTEXT, else what the server reports, else a safe guess."""
    forced = os.environ.get('TANDEM_CONTEXT')
    if forced and forced.isdigit():
        return int(forced)
    model = model or default_model()
    for m in models():
        if m['id'] == model and m['context']:
            return int(m['context'])
    return DEFAULT_CONTEXT.get(connect()['kind'], 8192)


# one completion --------------------------------------------------------------------------------
def strip_think(text):
    """The text without the reasoning blocks some models print before the answer."""
    text = THINK.sub('', text or '')
    end = None
    for end in THINK_END.finditer(text):                 # opening tag swallowed by the chat template
        pass
    if end:
        text = text[end.end():]
    if THINK_OPEN.match(text):                           # never closed: all of it is reasoning
        return ''
    return text.strip()


def _estimate(messages):
    return sum(len(str(m.get('content') or '')) for m in messages) // 4


def _create(model, messages, max_tokens, temperature, tools=None, schema=None):
    kwargs = {'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens}
    if tools:
        kwargs['tools'] = tools
    if schema:
        kwargs['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': schema}}
    return connect()['client'].chat.completions.create(**kwargs)


def chat(messages, tool='chat', model='', max_tokens=2048, temperature=0.1, tools=None, schema=None):
    """One completion. Returns (Reply, usage). Reasoning is never returned as the answer: when
    it eats the whole budget the call is repeated once with a larger one."""
    model = model or default_model()
    budget = max_tokens
    total = {'prompt': 0, 'completion': 0}
    for attempt in range(2):
        start = time.time()
        try:
            response = _create(model, messages, budget, temperature, tools, schema)
        except Exception as exc:
            raise ExecutorError(f'call to the local model failed ({connect()["name"]}, {model}): {exc}') from exc
        if not getattr(response, 'choices', None):
            raise ExecutorError('the model server returned no choice')
        choice = response.choices[0]
        usage = getattr(response, 'usage', None)
        message = choice.message
        raw = message.content or ''
        thought = bool(getattr(message, 'reasoning_content', None) or getattr(message, 'reasoning', None)
                       or THINK_END.search(raw) or THINK_OPEN.match(raw))
        used = {'prompt': getattr(usage, 'prompt_tokens', 0) or _estimate(messages),
                'completion': getattr(usage, 'completion_tokens', 0) or len(raw) // 4}
        total = {k: total[k] + used[k] for k in total}
        store.log(tool, kind='llm', model=model, prompt_tokens=used['prompt'], completion_tokens=used['completion'],
                  seconds=round(time.time() - start, 2))
        calls = [{'id': c.id or f'call_{n}', 'name': c.function.name, 'arguments': c.function.arguments or '{}'}
                 for n, c in enumerate(message.tool_calls or []) if getattr(c, 'function', None)]
        content = strip_think(raw)
        if content or calls:
            return Reply(content, calls, choice.finish_reason, thought), total
        if choice.finish_reason == 'length' and attempt == 0:
            budget = min(budget * 3, 16000)
            continue
        raise ExecutorError('the executor returned no answer (finish reason: %s)' % choice.finish_reason)
    raise ExecutorError('the executor returned no answer')


# structured answers ----------------------------------------------------------------------------
def parse_json(text, want=(dict, list)):
    """The first JSON value in a text, whatever surrounds it (fences, tags, prose)."""
    text = strip_think(text or '')
    try:
        data = json.loads(text)
        if isinstance(data, want):
            return data
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    for m in re.finditer(r'[{\[]', text):
        try:
            data, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(data, want):
            return data
    return None


def problem(data, schema):
    """Why `data` does not follow `schema` (top level and one level of items), or ''."""
    kinds = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'integer': int, 'number': (int, float)}
    want = schema.get('type')
    if isinstance(want, str) and want in kinds and not isinstance(data, kinds[want]):
        return f'the top level must be of type {want}'
    if isinstance(data, dict):
        missing = [k for k in schema.get('required', []) if k not in data]
        if missing:
            return 'missing keys: ' + ', '.join(missing)
        for key, sub in (schema.get('properties') or {}).items():
            kind = sub.get('type') if isinstance(sub, dict) else None
            if key in data and data[key] is not None and isinstance(kind, str) and kind in kinds:
                if not isinstance(data[key], kinds[kind]) or (kind in ('integer', 'number') and isinstance(data[key], bool)):
                    return f'"{key}" must be of type {kind}'
    return ''


def chat_json(messages, schema, tool='chat', model='', **kwargs):
    """A completion that must be JSON in a schema. The server enforces the schema when it can;
    otherwise the schema goes into the prompt, and a wrong answer gets one repair turn."""
    model = model or default_model()
    native = caps(model)['schema']
    total = {'prompt': 0, 'completion': 0}
    want = (list,) if schema.get('type') == 'array' else (dict,)
    guide = ('\n\nReply with one JSON value only, no prose and no code fence. It must follow this JSON schema:\n'
             + json.dumps(schema, separators=(',', ':')))
    turns = list(messages)
    why = 'no answer'
    for attempt in range(3):
        sent = turns if native else turns[:-1] + [{**turns[-1], 'content': str(turns[-1]['content']) + guide}]
        try:
            reply, used = chat(sent, tool=tool, model=model, schema=schema if native else None, **kwargs)
        except ExecutorError:
            if native and attempt == 0:                  # the server refused the schema: remember it, use the prompt
                native = False
                remember(model, schema=False)
                continue
            raise
        total = {k: total[k] + used[k] for k in total}
        data = parse_json(reply.content, want)
        why = 'it is not valid JSON' if data is None else problem(data, schema)
        if data is not None and not why:
            return data, total
        turns = list(messages) + [{'role': 'assistant', 'content': reply.content[:3000]},
                                  {'role': 'user', 'content': f'That answer cannot be used: {why}. Send the JSON again, complete and valid.'}]
    raise ExecutorError(f'the executor did not return valid JSON ({why})')


# what a model can do ---------------------------------------------------------------------------
PING = {'type': 'function', 'function': {'name': 'ping', 'description': 'Send a number.', 'parameters': {
    'type': 'object', 'properties': {'value': {'type': 'integer'}}, 'required': ['value']}}}
PROBE_SCHEMA = {'type': 'object', 'required': ['k7'], 'properties': {'k7': {'type': 'string', 'enum': ['a', 'b']}}}


def _caps_key(model):
    return f'{connect()["url"]}|{model}'


def remember(model, **changes):
    data = store.model_caps(_caps_key(model)) or {'tools': False, 'schema': False, 'thinking': False, 'tps': None}
    data.update(changes)
    store.save_model_caps(_caps_key(model), data)
    return data


def probe(model='', force=False):
    """Measure once what the model can do on this server:
    tools    it answers a tool request with a native tool call
    schema   the server forces a JSON schema on the output (constrained decoding)
    thinking it prints reasoning before the answer
    tps      tokens per second of generation"""
    model = model or default_model()
    known = store.model_caps(_caps_key(model))
    if known and known.get('probed') and not force:
        return known
    found = {'tools': False, 'schema': False, 'thinking': False, 'tps': None, 'probed': time.time(), 'notes': []}
    tokens = seconds = 0.0

    def one(label, messages, **more):
        nonlocal tokens, seconds
        start = time.time()
        try:
            reply, used = chat(messages, tool='probe', model=model, max_tokens=1200, temperature=0.0, **more)
        except ExecutorError as exc:
            found['notes'].append(f'{label}: {str(exc)[:160]}')
            return None
        tokens, seconds = used['completion'], time.time() - start     # the last call: the first may include the load
        found['thinking'] = found['thinking'] or reply.thought
        return reply

    # an unforced model answers "hello": only constrained decoding gives the odd key asked here
    reply = one('schema', [{'role': 'user', 'content': 'Say hello.'}], schema=PROBE_SCHEMA)
    data = parse_json(reply.content, (dict,)) if reply else None
    found['schema'] = bool(data) and data.get('k7') in ('a', 'b')
    reply = one('tools', [{'role': 'user', 'content': 'Call the tool ping with value 7.'}], tools=[PING])
    for call in (reply.calls if reply else []):
        try:
            found['tools'] = found['tools'] or (call['name'] == 'ping' and int(json.loads(call['arguments']).get('value')) == 7)
        except (ValueError, TypeError, AttributeError):
            pass
    if seconds > 0.5 and tokens:
        found['tps'] = round(tokens / seconds, 1)
    if not found['notes']:
        del found['notes']
    store.save_model_caps(_caps_key(model), found)
    return found


def caps(model=''):
    return probe(model)
