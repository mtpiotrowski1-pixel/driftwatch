"""Create responsive WebP/JPEG exports of the generated portal backgrounds."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copyfile

from PIL import Image

KIT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = KIT_ROOT / "backgrounds" / "v3" / "sources"
OUTPUT_DIR = KIT_ROOT / "backgrounds" / "v3" / "web"
APP_DIR = KIT_ROOT.parent / "web" / "src" / "assets" / "brand"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = []
    for stem in ("portal-hero-v3", "portal-ambient-v3"):
        source = SOURCE_DIR / f"{stem}.png"
        original = Image.open(source).convert("RGB")
        outputs = []
        variants = [(stem, original)]
        if stem == "portal-hero-v3":
            narrow = original.copy()
            narrow.thumbnail((960, 960), Image.Resampling.LANCZOS)
            variants.append(("portal-hero-mobile-v3", narrow))
        for name, image in variants:
            for extension in ("webp", "jpg"):
                destination = OUTPUT_DIR / f"{name}.{extension}"
                if extension == "webp":
                    image.save(destination, "WEBP", quality=84, method=6, exact=True)
                else:
                    image.save(destination, "JPEG", quality=88, optimize=True, progressive=True)
                copyfile(destination, APP_DIR / destination.name)
                outputs.append(
                    {
                        "path": destination.relative_to(KIT_ROOT).as_posix(),
                        "dimensions": list(image.size),
                        "bytes": destination.stat().st_size,
                        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    }
                )
        assets.append(
            {
                "source": source.relative_to(KIT_ROOT).as_posix(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_dimensions": list(original.size),
                "outputs": outputs,
            }
        )
    (OUTPUT_DIR / "exports.json").write_text(json.dumps(assets, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
