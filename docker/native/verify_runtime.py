"""Validate the complete pinned native inventory and removed library surfaces."""

import argparse
import json
import pyexpat
from pathlib import Path
from zoneinfo import ZoneInfo

parser = argparse.ArgumentParser()
parser.add_argument("role", choices=("api", "worker", "build"))
args = parser.parse_args()
expected = {}
for line in Path(f"/native/{args.role}.apk.lock").read_text().splitlines():
    if not line or line.startswith(("#", "!")):
        continue
    name, version = line.split("=", 1)
    expected[name.split("@", 1)[0]] = version
actual = {}
for block in Path("/lib/apk/db/installed").read_text().split("\n\n"):
    fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
    if fields.get("P"):
        actual[fields["P"]] = fields["V"]
if actual != expected:
    raise RuntimeError(f"Native inventory differs from {args.role} lock")
if pyexpat.version_info < (2, 9, 0):
    raise RuntimeError("CPython loaded an older embedded Expat")
for timezone in ("UTC", "Europe/Warsaw"):
    ZoneInfo(timezone)
for pattern in () if args.role == "build" else ("libacl.so*", "libcups.so*"):
    if list(Path("/usr/lib").glob(pattern)):
        raise RuntimeError(f"Unexpected removed library: {pattern}")
for executable in () if args.role == "build" else ("/usr/bin/perl", "/usr/bin/Xvfb"):
    if Path(executable).exists():
        raise RuntimeError(f"Unexpected removed executable: {executable}")
print(
    json.dumps(
        {
            "role": args.role,
            "native_packages": len(actual),
            "inventory": "exact lock",
            "python_expat": pyexpat.EXPAT_VERSION,
            "timezone_database": ["UTC", "Europe/Warsaw"],
            "removed_surfaces": [] if args.role == "build" else ["ACL", "CUPS", "Perl", "Xvfb"],
        }
    )
)
