"""CLI adapters for configurable benchmark orchestrators."""
import json
import subprocess


def legacy_scenario(value):
    return value if value.startswith('gemini_') else 'gemini_' + value


def neutral_scenario(value):
    return value.removeprefix('gemini_')


def validate(config):
    if config.get('cli', 'agy') not in {'agy', 'codex'}:
        raise ValueError('Unsupported orchestrator CLI; supported: agy, codex')
    if not config.get('model_id'):
        raise ValueError('orchestrator.model_id must be configured')


def collection_method(config):
    return config.get('cli', 'agy') + '_cli_json_usage'


def command(config, prompt, timeout, scenario, env):
    validate(config)
    cli = config.get('cli', 'agy')
    if cli == 'agy':
        return [cli, '--model', config['model_id'], '--output-format', 'json',
                '--dangerously-skip-permissions', '--new-project',
                '--print-timeout', f'{timeout}s', '-p', prompt]
    cmd = [cli, 'exec', '--model', config['model_id'], '--json', '--ephemeral',
           '--skip-git-repo-check', '--dangerously-bypass-approvals-and-sandbox']
    # Override MCP enablement per process, without mutating user configuration.
    servers = json.loads(subprocess.check_output([cli, 'mcp', 'list', '--json'], text=True, timeout=15))
    tandem = neutral_scenario(scenario) == 'tandem'
    if tandem and not any(s['name'] == 'tandem-mcp' for s in servers):
        raise RuntimeError('tandem-mcp must be configured for this CLI')
    cmd += ['-c', 'mcp_servers={}']
    if tandem:
        server = next(s for s in servers if s['name'] == 'tandem-mcp')
        transport = server['transport']
        if transport['type'] != 'stdio':
            raise ValueError('Benchmark isolation requires a stdio Tandem server')
        key = 'mcp_servers.tandem-mcp'
        cmd += ['-c', key + '.command=' + json.dumps(transport['command']),
                '-c', key + '.args=' + json.dumps(transport.get('args', [])),
                '-c', key + '.enabled=true']
        local_env = dict(transport.get('env') or {})
        for name in ('TANDEM_HOME', 'TANDEM_BASE_URL', 'TANDEM_MODEL', 'TANDEM_TIMEOUT'):
            local_env[name] = env[name]
        for name in ('TANDEM_MODEL_DIGEST', 'TANDEM_MODEL_DELEGATE'):
            local_env[name] = env['TANDEM_MODEL']
        for name, value in local_env.items():
            cmd += ['-c', key + '.env.' + name + '=' + json.dumps(value)]
    return cmd + [prompt]


def parse_output(config, output):
    events = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        except ValueError:
            continue
    if config.get('cli', 'agy') == 'agy':
        return events[-1] if events else None
    answer, usage, turns, thread = [], None, 0, None
    status = 'FAILED'
    for event in events:
        kind = event.get('type')
        if kind == 'thread.started':
            thread = event.get('thread_id')
        if kind == 'item.completed':
            item = event.get('item', {})
            if item.get('type') == 'agent_message':
                answer.append(item.get('text', ''))
        if kind == 'turn.completed':
            status = 'COMPLETED'
            turns += 1
            raw = event.get('usage')
            if raw and 'input_tokens' in raw and 'output_tokens' in raw:
                if usage is None:
                    usage = dict(input_tokens=0, output_tokens=0, cache_read_tokens=0)
                usage['input_tokens'] += raw['input_tokens']
                usage['output_tokens'] += raw['output_tokens']
                usage['cache_read_tokens'] += raw.get('cached_input_tokens', 0)
        if kind in {'turn.failed', 'error'}:
            status = 'FAILED'
    return dict(status=status, response='\n'.join(answer), usage=usage,
                num_turns=turns, conversation_id=thread)


def quota_exhausted(output):
    """Recognize explicit account quota exhaustion, not ordinary task failures."""
    text = output.lower()
    return any(marker in text for marker in (
        'usage limit reached', "you've hit your usage limit", 'usage_limit_reached',
        'usage limit exceeded', 'insufficient_quota',
    ))
