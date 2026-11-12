"""Client of the local model (LM Studio, OpenAI compatible) with accounting."""
import json
import os
import time
import urllib.request

from openai import OpenAI

from . import store

BASE_URL = os.environ.get('LM_STUDIO_BASE_URL', 'http://127.0.0.1:1234/v1')
client = OpenAI(base_url=BASE_URL, api_key=os.environ.get('LM_STUDIO_API_KEY', 'lm-studio'), timeout=900)


class ExecutorError(RuntimeError):
    pass


def models():
    """State of the models from the LM Studio REST API: id, loaded, context length."""
    try:
        with urllib.request.urlopen(BASE_URL.replace('/v1', '/api/v0') + '/models', timeout=5) as r:
            data = json.load(r)['data']
        return [{'id': m['id'], 'loaded': m.get('state') == 'loaded', 'type': m.get('type'),
                 'context': m.get('loaded_context_length') or m.get('max_context_length')} for m in data]
    except Exception:
        return [{'id': m.id, 'loaded': None, 'type': 'llm', 'context': None} for m in client.models.list().data]


def default_model():
    """The loaded chat model if there is one (no load delay), otherwise the first chat model."""
    forced = os.environ.get('TANDEM_MODEL')
    if forced:
        return forced
    chat_models = [m for m in models() if m['type'] != 'embeddings' and 'embed' not in m['id'].lower()]
    for m in chat_models:
        if m['loaded']:
            return m['id']
    if chat_models:
        return chat_models[0]['id']
    raise ExecutorError('no chat model in LM Studio')


def context_tokens(model):
    for m in models():
        if m['id'] == model and m['context']:
            return int(m['context'])
    return 16384


def chat(messages, tool='chat', model='', max_tokens=2048, temperature=0.1, tools=None, schema=None):
    """One completion. Returns (message, usage). The reasoning of the model is never returned
    as an answer: when it eats the whole budget the call is repeated once with a larger one."""
    model = model or default_model()
    kwargs = {'model': model, 'messages': messages, 'temperature': temperature}
    if tools:
        kwargs['tools'] = tools
    if schema:
        kwargs['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'answer', 'schema': schema}}
    budget = max_tokens
    for attempt in range(2):
        start = time.time()
        try:
            response = client.chat.completions.create(max_tokens=budget, **kwargs)
        except Exception as exc:
            raise ExecutorError(f'LM Studio call failed: {exc}') from exc
        choice = response.choices[0]
        usage = response.usage
        used = {'prompt': getattr(usage, 'prompt_tokens', 0) or 0, 'completion': getattr(usage, 'completion_tokens', 0) or 0}
        store.log(tool, kind='llm', model=model, prompt_tokens=used['prompt'], completion_tokens=used['completion'],
                  seconds=round(time.time() - start, 2))
        message = choice.message
        if (message.content or '').strip() or message.tool_calls:
            return message, used
        if choice.finish_reason == 'length' and attempt == 0:
            budget = min(budget * 3, 16000)
            continue
        raise ExecutorError('the executor returned no answer (finish reason: %s)' % choice.finish_reason)
    raise ExecutorError('the executor returned no answer')


def chat_json(messages, schema, tool='chat', **kwargs):
    message, used = chat(messages, tool=tool, schema=schema, **kwargs)
    text = (message.content or '').strip()
    try:
        return json.loads(text), used
    except ValueError:
        start, end = text.find('{'), text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1]), used
            except ValueError:
                pass
        raise ExecutorError('the executor did not return valid JSON')
