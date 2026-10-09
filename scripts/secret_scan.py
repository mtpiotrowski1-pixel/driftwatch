"""Pinned, redacted Gitleaks scans for outgoing files, staged changes and history."""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from hashlib import sha256
from pathlib import Path

VERSION = "8.30.1"
ARCHIVES = {
    ("Windows", "AMD64"): (
        "windows_x64.zip",
        "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
    ),
    ("Linux", "x86_64"): (
        "linux_x64.tar.gz",
        "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
    ),
    ("Linux", "aarch64"): (
        "linux_arm64.tar.gz",
        "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
    ),
    ("Darwin", "arm64"): (
        "darwin_arm64.tar.gz",
        "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
    ),
}
ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def _binary() -> Path:
    filename, expected = ARCHIVES[(platform.system(), platform.machine())]
    cache = Path(
        os.environ.get(
            "DRIFTWATCH_SECURITY_TOOLS_CACHE", Path.home() / ".cache" / "driftwatch-security"
        )
    )
    cache = cache / f"gitleaks-{VERSION}"
    binary_name = "gitleaks.exe" if platform.system() == "Windows" else "gitleaks"
    binary = cache / binary_name
    archive = cache / filename
    cache.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        url = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/gitleaks_{VERSION}_{filename}"
        with urllib.request.urlopen(url, timeout=60) as response:
            content = response.read()
        if sha256(content).hexdigest() != expected:
            raise RuntimeError("Gitleaks archive checksum mismatch")
        archive.write_bytes(content)
    content = archive.read_bytes()
    if sha256(content).hexdigest() != expected:
        raise RuntimeError("Cached Gitleaks archive checksum mismatch")
    # Extract only the named executable, never archive-controlled paths. Refresh
    # it from the verified archive instead of trusting a mutable cached binary.
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            executable = package.read(binary_name)
    else:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as package:
            member = package.extractfile(binary_name)
            if member is None:
                raise RuntimeError("Gitleaks executable absent from archive")
            executable = member.read()
    binary.write_bytes(executable)
    binary.chmod(0o755)
    return binary


def _outgoing(destination: Path) -> int:
    paths = _git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
    copied = 0
    for raw in paths:
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        original = ROOT / relative
        if not original.exists():  # Deleted tracked files do not ship.
            continue
        if original.is_symlink():
            raise RuntimeError(f"Review outgoing symlink before scanning: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        copied += 1
    return copied


def _scan(
    binary: Path, mode: str, source: Path, report: Path
) -> tuple[int, list[dict[str, object]]]:
    ignore = report.parent / "empty-gitleaks-ignore"
    ignore.touch()
    command = [str(binary), "git" if mode != "files" else "dir", "."]
    if mode == "history":
        command += ["--log-opts=--all"]
    elif mode == "staged":
        command += ["--pre-commit", "--staged"]
    command += [
        "--redact=100",
        "--no-banner",
        "--log-level=error",
        "--ignore-gitleaks-allow",
        "--gitleaks-ignore-path",
        str(ignore),
        "--config",
        str(ROOT / ".gitleaks.toml"),
        "--report-format=json",
        "--report-path",
        str(report),
    ]
    environment = os.environ.copy()
    # An ambient override must not silently weaken the committed policy.
    environment.pop("GITLEAKS_CONFIG", None)
    environment.pop("GITLEAKS_CONFIG_TOML", None)
    result = subprocess.run(command, cwd=source, env=environment, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Gitleaks {mode} failed with exit {result.returncode}; no clean result")
    if not report.exists():
        raise RuntimeError(f"Gitleaks {mode} produced no evidence report")
    findings = json.loads(report.read_text(encoding="utf-8"))
    safe = [
        {
            "kind": finding["RuleID"],
            "path": str(finding["File"]).removeprefix(str(source) + os.sep),
            "line": finding["StartLine"],
            "commit": finding.get("Commit", ""),
        }
        for finding in findings
    ]
    return result.returncode, safe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history", action="store_true", help="Scan every local Git ref; requires full history"
    )
    parser.add_argument(
        "--files", action="store_true", help="Scan tracked and nonignored untracked outgoing files"
    )
    parser.add_argument(
        "--staged", action="store_true", help="Scan only the staged diff for pre-commit"
    )
    parser.add_argument(
        "--report", type=Path, help="Write path/kind-only evidence outside the outgoing tree"
    )
    args = parser.parse_args()
    # Gitleaks also loads source/.gitleaksignore even when an explicit empty
    # ignore path is passed. Permit exceptions only in the reviewed TOML policy.
    if (ROOT / ".gitleaksignore").exists():
        raise RuntimeError("Fingerprint ignores are unsupported; review .gitleaks.toml instead")
    if args.report and ROOT in args.report.resolve().parents:
        parser.error("Keep secret-scan evidence outside the outgoing repository")
    selected = [mode for mode in ("history", "files", "staged") if getattr(args, mode)] or [
        "history",
        "files",
    ]
    if "history" in selected and _git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise RuntimeError("Full history scan requires a nonshallow checkout")
    binary = _binary()
    scans: list[dict[str, object]] = []
    safe_findings: list[dict[str, object]] = []
    summary: dict[str, object] = {
        "scanner": f"gitleaks {VERSION}",
        "scans": scans,
        "findings": safe_findings,
    }
    failed = False
    with tempfile.TemporaryDirectory(prefix="driftwatch-secret-scan-") as working:
        working_path = Path(working)
        for mode in selected:
            source = ROOT
            count = None
            if mode == "files":
                source = working_path / "outgoing"
                source.mkdir()
                count = _outgoing(source)
            code, findings = _scan(binary, mode, source, working_path / f"{mode}.json")
            failed |= code != 0
            scans.append({"mode": mode, "outgoing_file_count": count, "exit_code": code})
            safe_findings.extend({"scope": mode, **finding} for finding in findings)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        # Never print subprocess output or a provider-controlled error body.
        print(
            f"Secret scan incomplete: {type(exc).__name__}. See SECURITY.md for setup.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
