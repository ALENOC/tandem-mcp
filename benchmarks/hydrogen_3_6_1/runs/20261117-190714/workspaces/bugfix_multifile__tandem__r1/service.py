"""Build a validated ServiceConfig from a DSN and timeout."""
from config import ServiceConfig
from parser import parse_dsn
from validator import validate_port, validate_timeout


def build_config(dsn: str, ssl: bool = False, timeout_ms: int = 5000) -> ServiceConfig:
    raw = parse_dsn(dsn, ssl=ssl)
    port = validate_port(raw["port"])
    timeout = validate_timeout(timeout_ms)
    return ServiceConfig(
        host=raw["host"],
        port=port,
        ssl=raw["ssl"],
        timeout_ms=timeout,
        database=raw["database"],
    )
