"""Export the generated alpha logo for the app, device icons and brand kit.

The source is preserved verbatim. Exports trim empty margins and imperceptible
alpha-1 specks, fit the mark inside a square, and resize without recolouring.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from PIL import Image

KIT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = KIT_ROOT / "logo" / "v3" / "driftwatch-emblem-source.png"
LOGO_DIR = KIT_ROOT / "logo"
PUBLIC_DIR = KIT_ROOT.parent / "web" / "public"


def svg_image(png: bytes, *, size: int) -> str:
    encoded = base64.b64encode(png).decode("ascii")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {size} {size}" role="img" aria-label="Driftwatch">\n'
        f'  <image width="{size}" height="{size}" '
        f'href="data:image/png;base64,{encoded}" />\n'
        "</svg>\n"
    )


def export_logo() -> dict[str, object]:
    image = Image.open(SOURCE)
    if image.mode != "RGBA" or image.getchannel("A").getextrema()[0] != 0:
        raise ValueError("Logo source must contain a real transparent alpha channel")
    visible_bounds = image.getchannel("A").point(lambda value: 255 if value > 1 else 0).getbbox()
    if visible_bounds is None:
        raise ValueError("Logo source is entirely transparent")
    # The generated source has isolated alpha=1 specks at the canvas edges.
    # Keep extra source pixels around every visible edge before resizing.
    bounds = (
        max(0, visible_bounds[0] - 8),
        max(0, visible_bounds[1] - 8),
        min(image.width, visible_bounds[2] + 8),
        min(image.height, visible_bounds[3] + 8),
    )
    mark = image.crop(bounds)
    metadata: dict[str, object] = {
        "source": SOURCE.relative_to(KIT_ROOT).as_posix(),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "dimensions": list(image.size),
        "alpha": True,
        "trimmed_transparent_bounds": list(bounds),
        "visible_alpha_threshold": 1,
        "visible_bounds": list(visible_bounds),
        "export": "Lanczos resize, 6.25% clear space, original colours and alpha",
        "outputs": [],
    }
    outputs: list[dict[str, object]] = []
    for size in (16, 24, 32, 64, 128, 180, 192, 256, 512):
        fitted = mark.copy()
        inner_size = size - 2 * max(1, round(size / 16))
        fitted.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        destinations = [LOGO_DIR / f"driftwatch-mark-{size}.png"]
        if size in (32, 180, 192, 512):
            destinations.append(PUBLIC_DIR / "brand" / f"driftwatch-mark-{size}.png")
        if size in (64, 128, 256):
            destinations.extend(
                [
                    PUBLIC_DIR / "brand" / f"driftwatch-emblem-{size}.png",
                    PUBLIC_DIR / "brand" / f"driftwatch-emblem-{size}.webp",
                ]
            )
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.suffix == ".webp":
                canvas.save(destination, "WEBP", lossless=True, method=6, exact=True)
            else:
                canvas.save(destination, "PNG", optimize=True)
            outputs.append(
                {
                    "path": destination.relative_to(KIT_ROOT.parent).as_posix(),
                    "size": [size, size],
                    "bytes": destination.stat().st_size,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                }
            )
    primary_png = (LOGO_DIR / "driftwatch-mark-256.png").read_bytes()
    primary_svg = svg_image(primary_png, size=256)
    (LOGO_DIR / "driftwatch-mark.svg").write_text(primary_svg, encoding="utf-8")
    (PUBLIC_DIR / "brand" / "driftwatch-mark.svg").write_text(primary_svg, encoding="utf-8")
    favicon_png = (LOGO_DIR / "driftwatch-mark-32.png").read_bytes()
    (PUBLIC_DIR / "favicon.svg").write_text(svg_image(favicon_png, size=32), encoding="utf-8")
    metadata["outputs"] = outputs
    (SOURCE.parent / "exports.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    export_logo()


if __name__ == "__main__":
    main()
