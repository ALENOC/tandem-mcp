"""Central settings access."""

_DEFAULTS = {"timeout": 30, "retries": 3, "region": "eu-west-1", "batch": 50}


def load_settings(key, default=None):
    """Return the setting `key`, or `default` when unknown."""
    return _DEFAULTS.get(key, default)
