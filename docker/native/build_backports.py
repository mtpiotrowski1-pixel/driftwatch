"""Build hash-verified upstream fixes into normal APKs, retaining upstream versions.

The private tagged repository forces replacement even at the same version. APK
records and file checksums are generated from the rebuilt files, never edited
after installation. Source, patches and binary hashes remain in each package.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path("/native-build")
OUTPUT = Path("/native-packages")
EPOCH = 1791417600


def run(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def installed(name: str) -> dict[str, str]:
    for block in Path("/lib/apk/db/installed").read_text().split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        if fields.get("P") == name:
            return fields
    raise RuntimeError(f"Missing original package: {name}")


def tar_blob(root: Path, *, control: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for file in sorted(root.rglob("*")):
            info = archive.gettarinfo(str(file), arcname=file.relative_to(root).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = EPOCH
            if file.is_file() and not file.is_symlink():
                blob = file.read_bytes()
                if not control:
                    info.pax_headers["APK-TOOLS.checksum.SHA1"] = hashlib.sha1(blob).hexdigest()
                archive.addfile(info, io.BytesIO(blob))
            else:
                if file.is_symlink() and not control:
                    info.pax_headers["APK-TOOLS.checksum.SHA1"] = hashlib.sha1(
                        info.linkname.encode()
                    ).hexdigest()
                archive.addfile(info)
        end = archive.offset
    # APK v2 concatenates gzip streams. Its control TAR has no end markers;
    # otherwise apk stops before the independently checksummed data stream.
    content = buffer.getvalue()[:end] if control else buffer.getvalue()
    return gzip.compress(content, mtime=EPOCH)


def package(name: str, spec: dict[str, str], root: Path) -> None:
    metadata = installed(name)
    if metadata["V"] != spec["version"]:
        raise RuntimeError("Backport input package changed; review recipe")
    provenance: dict[str, object] = dict(
        spec, package=name, implementation="Driftwatch upstream security backport"
    )
    provenance["binaries"] = {
        str(file.relative_to(root)): sha(file.read_bytes())
        for file in sorted((root / "usr/lib").glob("*.so.*"))
        if not file.is_symlink()
    }
    proof = root / "usr/share/driftwatch/native" / f"{name}.json"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text(json.dumps(provenance, indent=2) + "\n")
    data = tar_blob(root)
    fields = {
        "pkgname": name,
        "pkgver": spec["version"],
        "arch": metadata["A"],
        "pkgdesc": f"{metadata['T']}; Driftwatch backport of {spec['cve']}",
        "url": spec["patch_source"],
        "license": metadata["L"],
        "origin": name,
        "maintainer": "Driftwatch maintainers (security backport)",
        "builddate": str(EPOCH),
        "size": str(
            sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink())
        ),
        "datahash": sha(data),
    }
    text = "".join(f"{key} = {value}\n" for key, value in fields.items())
    for label, key in (("depend", "D"), ("provides", "p")):
        text += "".join(f"{label} = {value}\n" for value in metadata.get(key, "").split())
    control_root = WORK / f"{name}-control"
    control_root.mkdir(exist_ok=True)
    (control_root / ".PKGINFO").write_text(text)
    target = OUTPUT / f"{name}-{spec['version']}.apk"
    target.write_bytes(tar_blob(control_root, control=True) + data)
    print(json.dumps({"package": name, "apk_sha256": sha(target.read_bytes()), **provenance}))


def main() -> None:
    WORK.mkdir()
    OUTPUT.mkdir()
    manifest = json.loads((HERE / "backports.json").read_text())
    for name, spec in manifest.items():
        with urllib.request.urlopen(spec["source"], timeout=120) as response:
            blob = response.read()
        if sha(blob) != spec["sha256"]:
            raise RuntimeError(f"Source digest mismatch: {name}")
        patch = HERE / "patches" / spec["patch"]
        if sha(patch.read_bytes()) != spec["patch_sha256"]:
            raise RuntimeError(f"Patch digest mismatch: {name}")
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:xz") as archive:
            archive.extractall(WORK, filter="data")
        source = WORK / spec["directory"]
        run("patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch), cwd=source)
        args = ["./configure", "--prefix=/usr", "--libdir=/usr/lib", "--disable-static"]
        if name == "libx11":
            args += [
                "--with-xcb",
                "--disable-thread-safety-constructor",
                "--disable-devel-docs",
                "--disable-specs",
                "--without-xmlto",
            ]
        run(*args, cwd=source)
        run("make", "-j4", cwd=source)
        run("make", "check", cwd=source)
        root = WORK / f"{name}-root"
        run("make", "install", f"DESTDIR={root}", cwd=source)
        for directory in ("usr/include", "usr/share/man", "usr/lib/pkgconfig"):
            shutil.rmtree(root / directory, ignore_errors=True)
        for file in (root / "usr/lib").glob("*.la"):
            file.unlink()
        for file in (root / "usr/lib").glob("*.so.*"):
            if not file.is_symlink():
                run("strip", "--strip-unneeded", str(file))
        license_dir = root / "usr/share/licenses" / name
        license_dir.mkdir(parents=True)
        shutil.copyfile(source / "COPYING", license_dir / "COPYING")
        package(name, spec, root)
    run(
        "apk",
        "index",
        "--allow-untrusted",
        "--output",
        str(OUTPUT / "APKINDEX.tar.gz"),
        *(str(p) for p in sorted(OUTPUT.glob("*.apk"))),
    )


if __name__ == "__main__":
    main()
