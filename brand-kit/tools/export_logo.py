"""Export the generated logo to the icons and image variants used by the app."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
KIT_ROOT = REPO_ROOT / "brand-kit"
SOURCE = KIT_ROOT / "logo" / "v3" / "driftwatch-emblem-source.png"
PUBLIC_DIR = REPO_ROOT / "web" / "public"


def export_logo() -> None:
    image = Image.open(SOURCE)
    if image.mode != "RGBA" or image.getchannel("A").getextrema()[0] != 0:
        raise ValueError("Logo source must contain a transparent alpha channel")
    visible_bounds = image.getchannel("A").point(lambda value: 255 if value > 1 else 0).getbbox()
    if visible_bounds is None:
        raise ValueError("Logo source is entirely transparent")
    # Ignore alpha-1 edge specks while retaining padding around visible pixels.
    bounds = (
        max(0, visible_bounds[0] - 8),
        max(0, visible_bounds[1] - 8),
        min(image.width, visible_bounds[2] + 8),
        min(image.height, visible_bounds[3] + 8),
    )
    mark = image.crop(bounds)
    outputs = []
    for size in (32, 64, 128, 180, 192, 256):
        fitted = mark.copy()
        inner_size = size - 2 * max(1, round(size / 16))
        fitted.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        destinations = []
        if size in (32, 180, 192):
            destinations.append(PUBLIC_DIR / "brand" / f"driftwatch-mark-{size}.png")
        if size in (64, 128, 256):
            destinations.append(PUBLIC_DIR / "brand" / f"driftwatch-emblem-{size}.webp")
        if size == 64:
            destinations.append(PUBLIC_DIR / "brand" / "driftwatch-emblem-64.png")
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.suffix == ".webp":
                canvas.save(destination, "WEBP", lossless=True, method=6, exact=True)
            else:
                canvas.save(destination, "PNG", optimize=True)
            outputs.append(destination)
        if size == 32:
            png = io.BytesIO()
            canvas.save(png, "PNG", optimize=True)
            encoded = base64.b64encode(png.getvalue()).decode("ascii")
            favicon = PUBLIC_DIR / "favicon.svg"
            favicon.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'viewBox="0 0 32 32" role="img" aria-label="Driftwatch">\n'
                '  <image width="32" height="32" '
                f'href="data:image/png;base64,{encoded}" />\n'
                "</svg>\n",
                encoding="utf-8",
            )
            outputs.append(favicon)
    manifest_path = KIT_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset = next(item for item in manifest["assets"] if item["id"] == "logo")
    asset["source_sha256"] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    asset["outputs"] = [
        {
            "path": path.relative_to(REPO_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(outputs)
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    export_logo()
