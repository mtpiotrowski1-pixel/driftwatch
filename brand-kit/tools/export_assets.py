"""Create delivery-friendly JPEG and WebP copies of the generated backgrounds."""

from pathlib import Path

from PIL import Image

KIT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = KIT_ROOT / "backgrounds" / "sources"
OUTPUT_DIR = KIT_ROOT / "backgrounds" / "web"


def export_background(source: Path) -> None:
    image = Image.open(source).convert("RGB")
    stem = source.stem
    image.save(
        OUTPUT_DIR / f"{stem}.webp",
        "WEBP",
        quality=82,
        method=6,
        exact=True,
    )
    image.save(
        OUTPUT_DIR / f"{stem}.jpg",
        "JPEG",
        quality=88,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for source in sorted(SOURCE_DIR.glob("*.png")):
        export_background(source)


if __name__ == "__main__":
    main()
