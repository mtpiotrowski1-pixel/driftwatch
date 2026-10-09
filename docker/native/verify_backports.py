"""Verify rebuilt library hashes without altering any scanner/package records."""

import hashlib
import json
from pathlib import Path

for name in ("libx11", "libxrender"):
    proof = json.loads(Path(f"/usr/share/driftwatch/native/{name}.json").read_text())
    for relative, expected in proof["binaries"].items():
        actual = hashlib.sha256((Path("/") / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Native backport binary mismatch: {name}: {relative}")
    print(f"Verified {name}: {proof['cve']}; original version {proof['version']}")
