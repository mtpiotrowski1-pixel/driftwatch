"""Reject unresolved ELF dependencies in the shipped browser and Playwright driver."""

import json
import struct
import subprocess
from pathlib import Path

import playwright


def main() -> None:
    loader = next(
        (
            path
            for path in (Path("/lib64/ld-linux-x86-64.so.2"), Path("/lib/ld-linux-x86-64.so.2"))
            if path.exists()
        ),
        None,
    )
    if loader is None:
        raise RuntimeError("The x86_64 glibc dynamic loader is absent")
    roots = [Path("/ms-playwright"), Path(playwright.__file__).parent / "driver"]
    checked = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            with path.open("rb") as file:
                header = file.read(64)
                if not header.startswith(b"\x7fELF"):
                    continue
                if header[4:6] != b"\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 62:
                    raise RuntimeError(f"Unexpected ELF architecture: {path}")
                offset = struct.unpack_from("<Q", header, 32)[0]
                size, count = struct.unpack_from("<HH", header, 54)
                dynamic = False
                for index in range(count):
                    file.seek(offset + index * size)
                    if struct.unpack("<I", file.read(4))[0] == 2:
                        dynamic = True
                if not dynamic:
                    continue
            result = subprocess.run(
                [str(loader), "--list", str(path)], capture_output=True, text=True
            )
            if result.returncode or "not found" in result.stdout + result.stderr:
                raise RuntimeError(
                    f"Unresolved browser dependencies: {path}\n{result.stdout}{result.stderr}"
                )
            checked.append(str(path))
    if not any(Path(path).name == "chrome-headless-shell" for path in checked):
        raise RuntimeError("Chromium headless shell is absent")
    if not any(Path(path).name == "node" for path in checked):
        raise RuntimeError("Playwright node driver is absent")
    print(json.dumps({"dynamic_elf_files": checked, "recursive_loader_resolution": "PASS"}))


if __name__ == "__main__":
    main()
