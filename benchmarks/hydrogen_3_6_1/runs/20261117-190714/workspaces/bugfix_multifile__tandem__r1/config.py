"""Application configuration dataclass."""
from dataclasses import dataclass


@dataclass
class ServiceConfig:
    host: str
    port: int
    ssl: bool
    timeout_ms: int
    database: str
