"""The documented helper configures first-run signup without fixed credentials."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_env.py"


def test_default_helper_runs_without_input_and_preserves_existing_env(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "bootstrap_env.py"
    script.parent.mkdir()
    script.write_bytes(_SOURCE.read_bytes())
    created = subprocess.run(
        [sys.executable, str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    original = (tmp_path / ".env").read_bytes()
    configuration = dict(
        line.split("=", 1)
        for line in original.decode().splitlines()
        if line and not line.startswith("#")
    )
    keys = [
        configuration[name]
        for name in (
            "DRIFTWATCH_SESSION_SECRET_KEY",
            "DRIFTWATCH_ENCRYPTION_KEY",
            "DRIFTWATCH_CAPTURE_WORKER_TOKEN",
        )
    ]
    assert len(set(keys)) == 3
    assert all(len(key) >= 48 for key in keys)
    assert configuration["DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED"] == "true"
    assert configuration["DRIFTWATCH_PUBLIC_REGISTRATION_ENABLED"] == "false"
    assert "DRIFTWATCH_INITIAL_ADMIN_EMAIL" not in configuration
    assert "DRIFTWATCH_INITIAL_ADMIN_PASSWORD" not in configuration
    repeated = subprocess.run(
        [sys.executable, str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert repeated.returncode != 0
    assert ".env already exists" in repeated.stderr
    assert (tmp_path / ".env").read_bytes() == original


def test_optional_seed_is_explicit_and_disables_signup_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = importlib.util.spec_from_file_location("isolated_bootstrap_env", _SOURCE)
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [str(_SOURCE), "--seed-admin"])
    monkeypatch.setattr("builtins.input", lambda _: "seeded-owner@example.test")
    monkeypatch.setattr(helper.getpass, "getpass", lambda _: "explicit-seed-test-password")
    helper.main()
    configuration = (tmp_path / ".env").read_text()
    assert "DRIFTWATCH_INITIAL_ADMIN_SIGNUP_ENABLED=false" in configuration
    assert "DRIFTWATCH_INITIAL_ADMIN_EMAIL=seeded-owner@example.test" in configuration
    assert "DRIFTWATCH_INITIAL_ADMIN_PASSWORD='explicit-seed-test-password'" in configuration
