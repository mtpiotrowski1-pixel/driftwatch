"""Canonical HTTP origins used to bind browser credentials to a destination."""

from urllib.parse import urlsplit


def http_origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A browser credential requires an HTTP(S) origin")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    suffix = f":{port}" if port is not None and port != (443 if scheme == "https" else 80) else ""
    return f"{scheme}://{host}{suffix}"
