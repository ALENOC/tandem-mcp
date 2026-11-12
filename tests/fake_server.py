"""A scripted OpenAI compatible server, to test the whole loop without a model.

It can behave like the kinds of local model that matter: with or without native tool calls,
with or without a JSON schema forced on the output, with or without printed reasoning."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Fake:
    def __init__(self, tools=True, schema=True, think=False, reject=False, flavour='openai', context=None):
        self.tools, self.schema, self.think, self.reject = tools, schema, think, reject
        self.flavour, self.context = flavour, context
        self.script, self.policy, self.requests = [], None, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, data, code=200):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == '/v1/models':
                    entry = {'id': 'fake-model'}
                    if fake.flavour == 'vllm' and fake.context:
                        entry['max_model_len'] = fake.context
                    return self.send({'data': [entry, {'id': 'fake-embed-model'}]})
                if fake.flavour == 'ollama' and self.path == '/api/tags':
                    return self.send({'models': [{'name': 'fake-model'}]})
                if fake.flavour == 'ollama' and self.path == '/api/ps':
                    return self.send({'models': [{'name': 'fake-model', 'context_length': fake.context}] if fake.context else []})
                if fake.flavour == 'llamacpp' and self.path == '/props':
                    return self.send({'default_generation_settings': {'n_ctx': fake.context}})
                if fake.flavour == 'lmstudio' and self.path == '/api/v0/models':
                    return self.send({'data': [{'id': 'fake-model', 'type': 'llm', 'state': 'loaded',
                                                'loaded_context_length': fake.context, 'max_context_length': 99999},
                                               {'id': 'fake-embed-model', 'type': 'embeddings', 'state': 'not-loaded'}]})
                self.send({'error': 'not found'}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fake.requests.append(body)
                if fake.reject and ('tools' in body and not fake.tools or 'response_format' in body and not fake.schema):
                    return self.send({'error': {'message': 'unsupported parameter'}}, 400)
                item = fake.answer(body)
                message = {'role': 'assistant', 'content': item.get('content', '')}
                if fake.think and message['content']:
                    message['content'] = '<think>\nLet me think {"tool": "nope"} about it.\n</think>\n\n' + message['content']
                if item.get('calls'):
                    message['tool_calls'] = [{'id': f'c{len(fake.requests)}_{n}', 'type': 'function',
                                              'function': {'name': name, 'arguments': args if isinstance(args, str) else json.dumps(args)}}
                                             for n, (name, args) in enumerate(item['calls'])]
                self.send({'id': 'x', 'object': 'chat.completion', 'model': body['model'],
                           'choices': [{'index': 0, 'message': message, 'finish_reason': item.get('finish', 'stop')}],
                           'usage': {'prompt_tokens': 50, 'completion_tokens': 20, 'total_tokens': 70}})

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.httpd.server_address[1]}/v1'
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def answer(self, body):
        names = [t['function']['name'] for t in body.get('tools', [])]
        props = (((body.get('response_format') or {}).get('json_schema') or {}).get('schema') or {}).get('properties', {})
        if names == ['ping']:                                    # the capability probe
            return {'calls': [('ping', {'value': 7})]} if self.tools else {'content': 'I cannot call tools.'}
        if 'k7' in props:
            return {'content': '{"k7": "a"}'} if self.schema else {'content': 'Hello!'}
        if self.policy:
            return self.shape(self.policy(body), body)
        if not self.script:
            return self.shape(('finish', {'summary': 'script ended', 'blocked': True}), body)
        item = self.script.pop(0)
        return self.shape(item(body) if callable(item) else item, body)

    def shape(self, item, body):
        """A (tool, args) pair becomes a native call or a JSON reply, as this model would give it."""
        if isinstance(item, tuple):
            if self.tools and 'tools' in body:
                return {'calls': [item]}
            return {'content': json.dumps({'tool': item[0], 'args': item[1]})}
        if isinstance(item, str):
            return {'content': item}
        return item

    def close(self):
        self.httpd.shutdown()
