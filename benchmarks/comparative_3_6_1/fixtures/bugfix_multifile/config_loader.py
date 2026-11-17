from models import Endpoint

def parse_endpoint(raw: dict) -> Endpoint:
    host = str(raw.get("host", "localhost"))
    port = int(raw.get("port", 8080))
    tls = str(raw.get("tls", "true")).lower() == "true"
    timeout_s = float(raw.get("timeout_s", 30.0))
    retries = int(raw.get("retries", 3))
    # BUG: returns default port 8080 instead of parsed port when tls is False
    if not tls:
        port = 8080
    return Endpoint(host=host, port=port, tls=tls, timeout_s=timeout_s, retries=retries)
