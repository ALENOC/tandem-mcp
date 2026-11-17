"""Validation helpers for ServiceConfig."""


def validate_port(port: int) -> int:
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError(f"Invalid port: {port}")
    return port


def validate_timeout(timeout_ms: int) -> int:
    # BUG: rejects 0, which is a valid "no timeout" setting
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise ValueError(f"Invalid timeout_ms: {timeout_ms}")
    return timeout_ms
