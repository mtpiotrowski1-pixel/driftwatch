"""Export the decorative portal and recovery backgrounds used by the app."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
KIT_ROOT = REPO_ROOT / "brand-kit"
APP_DIR = REPO_ROOT / "web" / "src" / "assets" / "brand"


def output_metadata(paths: list[Path]) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(paths)
    ]


def main() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = KIT_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for stem, asset_id in (
        ("portal-hero-v3", "portal-hero"),
        ("portal-ambient-v3", "portal-ambient"),
    ):
        source = KIT_ROOT / "backgrounds" / "v3" / "sources" / f"{stem}.png"
        original = Image.open(source).convert("RGB")
        outputs = []
        variants = [(stem, original)]
        if asset_id == "portal-hero":
            narrow = original.copy()
            narrow.thumbnail((960, 960), Image.Resampling.LANCZOS)
            variants.append(("portal-hero-mobile-v3", narrow))
        for name, image in variants:
            for extension in ("webp", "jpg"):
                destination = APP_DIR / f"{name}.{extension}"
                if extension == "webp":
                    image.save(destination, "WEBP", quality=84, method=6, exact=True)
                else:
                    image.save(destination, "JPEG", quality=88, optimize=True, progressive=True)
                outputs.append(destination)
        asset = next(item for item in manifest["assets"] if item["id"] == asset_id)
        asset["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        asset["outputs"] = output_metadata(outputs)
    recovery_source = KIT_ROOT / "backgrounds" / "sources" / "recovery-light-signal.png"
    recovery = Image.open(recovery_source).convert("RGB")
    recovery_output = APP_DIR / "recovery-light-signal.webp"
    recovery.save(recovery_output, "WEBP", quality=82, method=6, exact=True)
    asset = next(item for item in manifest["assets"] if item["id"] == "recovery")
    asset["source_sha256"] = hashlib.sha256(recovery_source.read_bytes()).hexdigest()
    asset["outputs"] = output_metadata([recovery_output])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
