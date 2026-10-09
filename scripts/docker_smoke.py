"""Exercise release images against owned fixtures, including actual socket filtering."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "api": "driftwatch:release",
    "worker": "driftwatch-capture:release",
    "firewall": "driftwatch-firewall:release",
}
FIXTURE = """from http.server import BaseHTTPRequestHandler, HTTPServer
version = 1
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global version
        if self.path == '/advance':
            version = 2
        body = f'<html><main>Available stock: {version}</main></html>'.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
"""


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        # Docker commands may include ephemeral credentials; do not echo them.
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr[-1800:]}")
    # docker logs preserves the container's stdout/stderr streams separately.
    return (result.stdout + (result.stderr if args[0] == "logs" else "")).strip()


def wait_for(probe, description: str, seconds: int = 90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value:
                return value
        except (OSError, ValueError, RuntimeError, urllib.error.HTTPError):
            pass
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {description}")


class API:
    def __init__(self, url: str):
        self.url = url
        self.cookies: dict[str, str] = {}
        self.organization: int | None = None

    def call(self, path: str, payload=None, *, method: str | None = None):
        headers = {"Origin": "http://localhost:8000"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        if self.organization is not None:
            headers["X-Acting-Org"] = str(self.organization)
        request = urllib.request.Request(
            self.url + path,
            headers=headers,
            data=None if payload is None else json.dumps(payload).encode(),
            method=method,
        )
        with urllib.request.urlopen(request, timeout=100) as response:
            for header in response.headers.get_all("Set-Cookie", []):
                cookie = SimpleCookie()
                cookie.load(header)
                self.cookies.update({key: item.value for key, item in cookie.items()})
            body = response.read()
        return json.loads(body) if body else None


def totp(secret: str) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(
        6
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()
    if not args.no_build:
        for target, image in (
            ("runtime", IMAGES["api"]),
            ("capture-worker", IMAGES["worker"]),
            ("capture-firewall", IMAGES["firewall"]),
        ):
            docker("build", "--target", target, "--tag", image, ".")
    prefix = "driftwatch-smoke-" + uuid4().hex[:10]
    containers: list[str] = []
    networks: list[str] = []
    redacted_values: list[str] = []
    hardening = [
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
    ]
    with tempfile.TemporaryDirectory(prefix=prefix) as temporary:
        fixture = Path(temporary) / "fixture.py"
        fixture.write_text(FIXTURE, encoding="utf-8")
        try:
            # Public-class address is routed only to our isolated Docker fixture.
            for label, subnet in (
                ("public", "93.184.216.0/24"),
                ("private", "10.98.0.0/24"),
                ("cgnat", "100.64.90.0/24"),
                ("metadata", "169.254.90.0/24"),
            ):
                name = prefix + "-" + label
                docker("network", "create", "--internal", "--subnet", subnet, name)
                networks.append(name)
            fixture_name = prefix + "-fixture"
            docker(
                "run",
                "-d",
                "--name",
                fixture_name,
                "--network",
                networks[0],
                "--ip",
                "93.184.216.10",
                "--mount",
                f"type=bind,source={fixture},target=/fixture.py,readonly",
                "--entrypoint",
                "python",
                IMAGES["api"],
                "/fixture.py",
            )
            containers.append(fixture_name)
            for network, address in zip(
                networks[1:], ("10.98.0.10", "100.64.90.10", "169.254.90.10"), strict=True
            ):
                docker("network", "connect", "--ip", address, network, fixture_name)
            firewall = prefix + "-firewall"
            docker(
                "run",
                "-d",
                "--name",
                firewall,
                "--network",
                networks[0],
                *hardening,
                "--cap-add",
                "NET_ADMIN",
                IMAGES["firewall"],
            )
            containers.append(firewall)
            for network in networks[1:]:
                docker("network", "connect", network, firewall)
            wait_for(
                lambda: (
                    json.loads(docker("inspect", firewall))[0]["State"]["Health"]["Status"]
                    == "healthy"
                ),
                "firewall",
            )
            token, password = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
            session_key, encryption_key = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
            redacted_values.extend((token, password, session_key, encryption_key))
            worker = prefix + "-worker"
            docker(
                "run",
                "-d",
                "--name",
                worker,
                "--network",
                "container:" + firewall,
                *hardening,
                "--shm-size",
                "256m",
                "--no-healthcheck",
                "--env",
                "DRIFTWATCH_CAPTURE_WORKER_TOKEN=" + token,
                IMAGES["worker"],
            )
            containers.append(worker)
            # First prove all fixture sockets are live without the firewall.
            control = prefix + "-control"
            docker(
                "run",
                "-d",
                "--name",
                control,
                "--network",
                networks[0],
                "--entrypoint",
                "sleep",
                IMAGES["api"],
                "infinity",
            )
            containers.append(control)
            for network in networks[1:]:
                docker("network", "connect", network, control)
            socket_probe = (
                "import socket; s=socket.create_connection(({address!r},8080),timeout=3); s.close()"
            )
            for address in ("93.184.216.10", "10.98.0.10", "100.64.90.10", "169.254.90.10"):
                docker("exec", control, "python", "-c", socket_probe.format(address=address))
            docker("exec", worker, "python", "-c", socket_probe.format(address="93.184.216.10"))
            for address, port in (
                ("10.98.0.10", 8080),
                ("100.64.90.10", 8080),
                ("169.254.90.10", 8080),
                ("169.254.169.254", 80),
                ("127.0.0.1", 8090),
            ):
                probe = f"""import socket
try:
    socket.create_connection(({address!r}, {port}), timeout=3)
except OSError:
    pass
else:
    raise AssertionError('Forbidden socket connected')
"""
                docker("exec", worker, "python", "-c", probe)
            print("Owned fixture sockets and worker packet boundary passed", flush=True)
            # Match Compose: the API has ordinary app egress as well as the
            # internal worker-control network. An internal-only network does
            # not expose the published port on all Docker Desktop backends.
            app_network = prefix + "-app-egress"
            docker("network", "create", app_network)
            networks.append(app_network)
            api_name = prefix + "-api"
            firewall_ip = json.loads(docker("inspect", firewall))[0]["NetworkSettings"]["Networks"][
                networks[1]
            ]["IPAddress"]
            docker(
                "run",
                "-d",
                "--name",
                api_name,
                "--network",
                app_network,
                *hardening,
                "--tmpfs",
                "/data:rw,nosuid,nodev,size=256m,uid=10001,gid=10001",
                "--publish",
                "127.0.0.1::8000",
                "--env",
                "DRIFTWATCH_BASE_URL=http://localhost:8000",
                "--env",
                "DRIFTWATCH_SESSION_SECRET_KEY=" + session_key,
                "--env",
                "DRIFTWATCH_ENCRYPTION_KEY=" + encryption_key,
                "--env",
                "DRIFTWATCH_INITIAL_ADMIN_EMAIL=smoke@example.com",
                "--env",
                "DRIFTWATCH_INITIAL_ADMIN_PASSWORD=" + password,
                "--env",
                f"DRIFTWATCH_CAPTURE_WORKER_URL=http://{firewall_ip}:8090",
                "--env",
                "DRIFTWATCH_CAPTURE_WORKER_TOKEN=" + token,
                "--env",
                "DRIFTWATCH_CAPTURE_WORKER_ALLOW_INSECURE_HTTP=true",
                "--env",
                "DRIFTWATCH_PICKER_ENABLED=false",
                IMAGES["api"],
            )
            containers.append(api_name)
            docker("network", "connect", networks[1], api_name)
            bindings = wait_for(
                lambda: (
                    json.loads(docker("inspect", api_name))[0]["NetworkSettings"]["Ports"].get(
                        "8000/tcp"
                    )
                    or []
                ),
                "API published port",
            )
            port = bindings[0]["HostPort"]
            api = API("http://127.0.0.1:" + port)
            wait_for(lambda: api.call("/healthz")["status"] == "ok", "complete API readiness")
            api.call("/api/auth/login", {"email": "smoke@example.com", "password": password})
            api.call("/api/auth/step-up", {"password": password})
            factor = api.call("/api/auth/totp/setup", {})["secret"]
            api.call("/api/auth/totp/enable", {"code": totp(factor)})
            api.call("/api/auth/step-up", {"password": password, "totp_code": totp(factor)})
            api.call("/api/settings", {"email_provider": "log"}, method="PUT")
            api.organization = api.call("/api/organizations")[0]["id"]
            api.call("/api/auth/step-up", {"password": password, "totp_code": totp(factor)})
            api.call(
                "/api/support-access",
                {"reason": "Owned release fixture smoke test", "ticket": "release-smoke"},
            )
            recipient = api.call("/api/recipients", {"email": "smoke-diff@example.com"})
            site = api.call(
                "/api/sites",
                {
                    "url": "http://93.184.216.10:8080/",
                    "css_selector": "main",
                    "analysis_mode": "disabled",
                    "notification_mode": "always",
                    "recipient_ids": [recipient["id"]],
                    "enabled": False,
                },
            )
            path = f"/api/sites/{site['id']}/check"
            assert api.call(path, {})["status"] == "baseline"
            docker(
                "exec",
                control,
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://93.184.216.10:8080/advance').read()",
            )
            changed = api.call(path, {})
            assert (
                changed["status"] == "changed"
                and changed["change_id"]
                and changed["significant"] is None
            )
            detail = api.call(f"/api/changes/{changed['change_id']}")
            assert detail["analysis_status"] == "disabled" and not detail["analysis_runs"]
            assert detail["notified_at"] and changed["notified"] and changed["recipients"] == 1
            deliveries = api.call(f"/api/notifications?change_id={changed['change_id']}")
            assert len(deliveries) == 1 and deliveries[0]["status"] == "sent"
            assert deliveries[0]["channel"] == "log"
            assert deliveries[0]["recipient_email"] == "smoke-diff@example.com"
            usage = api.call("/api/usage/summary")
            assert usage["calls"] == 0 and usage["total_tokens"] == 0
            assert usage["total_cost_usd"] == 0 and usage["unknown_cost_calls"] == 0
            for name in (api_name, worker):
                state = json.loads(docker("inspect", name))[0]
                assert state["HostConfig"]["ReadonlyRootfs"] and state["Config"]["User"] not in (
                    "",
                    "0",
                    "root",
                )
                assert state["HostConfig"]["CapDrop"] == ["ALL"]
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "socket_boundary": ["private", "CGNAT", "metadata", "loopback"],
                        "allowed": "owned public-class fixture",
                        "pipeline": ["baseline", "changed", "AI disabled"],
                        "providers_called": [],
                        "delivery": "explicit LogChannel, SENT persisted",
                        "ai_usage_calls": 0,
                        "worker": "nonroot, read-only, capdrop ALL",
                    },
                    indent=2,
                )
            )
        except BaseException:
            # Report only these owned fixtures, with every generated credential
            # redacted. Do not print docker inspect environment blocks.
            for name in containers:
                try:
                    state = json.loads(docker("inspect", name))[0]["State"]
                    logs = docker("logs", "--tail", "40", name)
                    for value in redacted_values:
                        logs = logs.replace(value, "[redacted]")
                    print(f"Owned {name}: {state['Status']}, exit {state['ExitCode']}", flush=True)
                    print(logs[-4000:], flush=True)
                except (OSError, ValueError, RuntimeError):
                    print(f"Owned fixture diagnostics unavailable: {name}", flush=True)
            raise
        finally:
            for name in reversed(containers):
                subprocess.run(["docker", "rm", "--force", "--volumes", name], capture_output=True)
            for name in reversed(networks):
                subprocess.run(["docker", "network", "rm", name], capture_output=True)


if __name__ == "__main__":
    main()
