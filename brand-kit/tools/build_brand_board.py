"""Build visual contact sheets for the standalone Driftwatch brand kit."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

KIT_ROOT = Path(__file__).resolve().parents[1]
BACKGROUND_DIR = KIT_ROOT / "backgrounds" / "v3" / "web"
LOGO_DIR = KIT_ROOT / "logo"
PREVIEW_DIR = KIT_ROOT / "previews"

FONT_REGULAR = Path("C:/Windows/Fonts/segoeui.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/segoeuib.ttf")


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    windows_font = FONT_BOLD if bold else FONT_REGULAR
    if windows_font.is_file():
        return ImageFont.truetype(str(windows_font), size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


def rounded_image(image: Image.Image, size: tuple[int, int], radius: int) -> Image.Image:
    fitted = ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *size), radius=radius, fill=255)
    fitted.putalpha(mask)
    return fitted


def background_contact_sheet() -> None:
    canvas = Image.new("RGB", (1800, 1300), "#111511")
    draw = ImageDraw.Draw(canvas)
    draw.text((70, 52), "Emerald Portal — background set", fill="#ffffff", font=font(52, bold=True))
    draw.text(
        (70, 120),
        "Photo-real editorial layers · no text · responsive-safe negative space",
        fill="#aeb8af",
        font=font(25),
    )

    hero = rounded_image(Image.open(BACKGROUND_DIR / "portal-hero-v3.webp"), (1060, 596), 24)
    auth = rounded_image(Image.open(BACKGROUND_DIR / "portal-hero-v3.webp"), (500, 596), 24)
    recovery = rounded_image(Image.open(BACKGROUND_DIR / "portal-ambient-v3.webp"), (1060, 360), 24)
    mobile = rounded_image(
        Image.open(BACKGROUND_DIR / "portal-hero-mobile-v3.webp"), (500, 360), 24
    )
    canvas.paste(hero, (70, 190), hero)
    canvas.paste(auth, (1230, 190), auth)
    canvas.paste(recovery, (70, 860), recovery)
    canvas.paste(mobile, (1230, 860), mobile)

    labels = [
        ((70, 802), "HERO · DESKTOP"),
        ((1230, 802), "AUTH · DESKTOP"),
        ((70, 1236), "WORKSPACE · LIGHT"),
        ((1230, 1236), "HERO · MOBILE"),
    ]
    for position, label in labels:
        draw.text(position, label, fill="#b4e653", font=font(21, bold=True))

    canvas.save(PREVIEW_DIR / "background-set.png", optimize=True)


def brand_board() -> None:
    canvas = Image.new("RGB", (2200, 1800), "#f3f5f0")
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle((50, 50, 2150, 520), radius=34, fill="#111511")
    mark = Image.open(LOGO_DIR / "driftwatch-mark-192.png").convert("RGBA")
    canvas.paste(mark, (120, 120), mark)
    draw.text((350, 112), "Driftwatch", fill="#ffffff", font=font(110, bold=True))
    draw.text((355, 255), "EMERALD PORTAL", fill="#b4e653", font=font(30, bold=True))
    draw.text(
        (355, 315),
        "Rzeźbiarski monogram D. Jedna precyzyjna zmiana,\n"
        "gdy obserwowana strona zmienia znaczenie.",
        fill="#aeb8af",
        font=font(30),
        spacing=12,
    )

    swatches = [
        ("Night Watch", "#111511"),
        ("Ivory Canvas", "#F5F4ED"),
        ("Signal Lime", "#B4E653"),
        ("Emerald Glass", "#0B6753"),
        ("Champagne Edge", "#E7D8B6"),
    ]
    x = 80
    for name, color in swatches:
        draw.rounded_rectangle((x, 600, x + 350, 760), radius=22, fill=color)
        text_color = "#ffffff" if color == "#111511" else "#151915"
        draw.text((x + 24, 632), name, fill=text_color, font=font(24, bold=True))
        draw.text((x + 24, 684), color, fill=text_color, font=font(21))
        x += 420

    hero = rounded_image(Image.open(BACKGROUND_DIR / "portal-hero-v3.webp"), (1250, 704), 30)
    auth = rounded_image(Image.open(BACKGROUND_DIR / "portal-ambient-v3.webp"), (560, 704), 30)
    canvas.paste(hero, (80, 850), hero)
    canvas.paste(auth, (1560, 850), auth)

    draw.text((80, 1585), "LANDING HERO", fill="#4f651a", font=font(24, bold=True))
    draw.text((1560, 1585), "WORKSPACE CANVAS", fill="#4f651a", font=font(24, bold=True))
    draw.text(
        (80, 1660),
        "Sculptural glass and satin metal for public and workspace surfaces. "
        "Real controls and content stay interactive.",
        fill="#58625a",
        font=font(28),
    )

    canvas.save(PREVIEW_DIR / "brand-board.png", optimize=True)


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    background_contact_sheet()
    brand_board()


if __name__ == "__main__":
    main()
