"""Create a private local configuration without replacing existing secrets."""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-admin",
        action="store_true",
        help="Optional: create the first administrator from private environment credentials.",
    )
    arguments = parser.parse_args()
    destination = ROOT / ".env"
    if destination.exists():
        raise SystemExit(".env already exists; review it manually. No configuration was replaced.")
    administrator_lines = ["DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED=true"]
    if arguments.seed_admin:
        email = input("Initial administrator email: ").strip()
        if "@" not in email or any(char in email for char in "\r\n\"' #"):
            raise SystemExit("Enter a valid email address.")
        password = getpass.getpass("Initial administrator password (at least 16 characters): ")
        if len(password) < 16 or any(char in password for char in "\r\n\"'"):
            raise SystemExit("Use at least 16 characters without quotes or newlines.")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("Passwords do not match.")
        administrator_lines = [
            "DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED=false",
            "DRIFTWATCH_INITIAL_ADMIN_EMAIL=" + email,
            "DRIFTWATCH_INITIAL_ADMIN_PASSWORD='" + password + "'",
        ]
    content = "\n".join(
        [
            "# Private configuration. Never commit or publish this file.",
            "DRIFTWATCH_BASE_URL=http://localhost:8000",
            "DRIFTWATCH_SESSION_SECRET_KEY=" + secrets.token_urlsafe(48),
            "DRIFTWATCH_ENCRYPTION_KEY=" + secrets.token_urlsafe(48),
            "DRIFTWATCH_CAPTURE_WORKER_TOKEN=" + secrets.token_urlsafe(48),
            *administrator_lines,
            "DRIFTWATCH_PUBLIC_REGISTRATION_ENABLED=false",
            "DRIFTWATCH_PICKER_ENABLED=false",
            "",
        ]
    )
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Created .env with three independent random keys. Keep the encryption key with backups.")
    print("Run: docker compose up --build -d")
    if not arguments.seed_admin:
        print("Open http://localhost:8000 and register the first account to own this instance.")
    print("Claim ownership before exposing the service; later signups are closed by default.")
    print("Enroll two-factor authentication and save the recovery codes after signing in.")


if __name__ == "__main__":
    main()
