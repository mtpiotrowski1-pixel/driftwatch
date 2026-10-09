"""Transport-level proof that HTTP pinning preserves TLS authentication."""

from __future__ import annotations

import asyncio
import ssl
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from driftwatch.security.outbound import PinnedHTTPEndpoint

_LOGICAL_HOST = "hook.example.test"


async def test_pinned_https_authenticates_logical_host_without_dns(
    tmp_path: Path,
) -> None:
    certificate_path, key_path = _self_signed_server_certificate(tmp_path)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate_path, key_path)
    captured: dict[str, str | None] = {}

    def capture_sni(_: ssl.SSLObject, server_name: str | None, __: ssl.SSLContext) -> None:
        captured["sni"] = server_name

    server_context.set_servername_callback(capture_sni)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_head = await reader.readuntil(b"\r\n\r\n")
            headers = request_head.decode("ascii").split("\r\n")
            captured["host"] = next(
                line.partition(":")[2].strip()
                for line in headers
                if line.lower().startswith("host:")
            )
            writer.write(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
            await writer.drain()
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server_context)
    socket_address = server.sockets[0].getsockname()
    port = int(socket_address[1])
    logical_url = f"https://{_LOGICAL_HOST}:{port}/hook"
    endpoint = PinnedHTTPEndpoint(
        logical_url=logical_url,
        address="127.0.0.1",
        tls_server_name=_LOGICAL_HOST,
    )
    client_context = ssl.create_default_context(cafile=str(certificate_path))

    try:
        async with (
            server,
            httpx.AsyncClient(
                verify=client_context,
                # This checks TLS identity and pinning, not handshake speed.
                # Parallel CI may delay the test-owned loopback TLS server.
                timeout=10.0,
                trust_env=False,
            ) as client,
        ):
            request = client.build_request("POST", logical_url, content=b"{}")
            endpoint.pin(request)
            response = await client.send(request)
    finally:
        server.close()
        await server.wait_closed()

    assert response.status_code == 204
    assert captured == {
        "host": f"{_LOGICAL_HOST}:{port}",
        "sni": _LOGICAL_HOST,
    }


def _self_signed_server_certificate(tmp_path: Path) -> tuple[Path, Path]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _LOGICAL_HOST)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=5))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(_LOGICAL_HOST)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    certificate_path = tmp_path / "server.pem"
    key_path = tmp_path / "server-key.pem"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return certificate_path, key_path
