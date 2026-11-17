"""DSN parser for service configuration."""
from urllib.parse import urlparse


def parse_dsn(dsn: str, ssl: bool = False) -> dict:
    """Parse a postgres-like DSN into host, port, database, and ssl."""
    parsed = urlparse(dsn)
    if not parsed.hostname:
        raise ValueError(f"Missing host in DSN: {dsn!r}")
    port = parsed.port if parsed.port is not None else (5433 if ssl else 5432)
    db = parsed.path.lstrip("/") or "default"
    return {
        "host": parsed.hostname,
        "port": port,
        "database": db,
        "ssl": ssl,
    }
