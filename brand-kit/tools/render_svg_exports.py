"""Render PNG fallbacks and contact sheets from the SVG brand assets."""

import argparse
from pathlib import Path
from shutil import copyfile

from playwright.sync_api import Browser, Page, sync_playwright

KIT_ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = KIT_ROOT / "logo"
ILLUSTRATION_DIR = KIT_ROOT / "illustrations"
PREVIEW_DIR = KIT_ROOT / "previews"
PUBLIC_DIR = KIT_ROOT.parent / "web" / "public"
GENERATED_LOGO = LOGO_DIR / "v3" / "driftwatch-emblem-source.png"


def svg_markup(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def render_svg(
    page: Page,
    source: Path,
    destination: Path,
    *,
    width: int,
    height: int,
    color: str | None = None,
) -> None:
    color_rule = f"color:{color};" if color else ""
    page.set_content(
        f"""
        <style>
          html, body {{ margin: 0; background: transparent; {color_rule} }}
          svg {{ display: block; width: {width}px; height: {height}px; }}
        </style>
        {svg_markup(source)}
        """
    )
    page.locator("svg").screenshot(path=str(destination), omit_background=True)


def render_logo_exports(page: Page) -> None:
    primary = LOGO_DIR / "driftwatch-mark.svg"
    mono = LOGO_DIR / "driftwatch-mark-mono.svg"
    if not GENERATED_LOGO.is_file():
        for size in (16, 24, 32, 64, 180, 192, 512):
            render_svg(
                page,
                primary,
                LOGO_DIR / f"driftwatch-mark-{size}.png",
                width=size,
                height=size,
            )
    render_svg(
        page,
        mono,
        LOGO_DIR / "driftwatch-mark-mono-dark-512.png",
        width=512,
        height=512,
        color="#151915",
    )
    render_svg(
        page,
        mono,
        LOGO_DIR / "driftwatch-mark-mono-light-512.png",
        width=512,
        height=512,
        color="#ffffff",
    )
    # Browser, README and app icons use the same geometry as the brand kit.
    copyfile(primary, PUBLIC_DIR / "brand" / primary.name)
    if not GENERATED_LOGO.is_file():
        copyfile(primary, PUBLIC_DIR / "favicon.svg")
    for size in (32, 180, 192, 512):
        name = f"driftwatch-mark-{size}.png"
        copyfile(LOGO_DIR / name, PUBLIC_DIR / "brand" / name)


def render_illustration_exports(page: Page) -> None:
    for source in sorted(ILLUSTRATION_DIR.glob("*.svg")):
        render_svg(
            page,
            source,
            ILLUSTRATION_DIR / f"{source.stem}.png",
            width=960,
            height=640,
        )


def render_logo_preview(page: Page) -> None:
    mark = svg_markup(LOGO_DIR / "driftwatch-mark.svg")
    mono = svg_markup(LOGO_DIR / "driftwatch-mark-mono.svg")
    sizes = "".join(f'<span style="--size:{size}px">{mark}</span>' for size in (16, 24, 32, 48))
    page.set_viewport_size({"width": 1440, "height": 760})
    page.set_content(
        f"""
        <style>
          * {{ box-sizing: border-box; }}
          html, body {{ margin: 0; font-family: "Segoe UI Variable", "Segoe UI", sans-serif; }}
          main {{
            display: grid; grid-template-columns: 1fr 1fr; width: 1440px; height: 760px;
          }}
          section {{ display: flex; flex-direction: column;
            justify-content: space-between; padding: 72px; }}
          .dark {{ background: #111511; color: #fff; }}
          .light {{ background: #f5f4ed; color: #151915; }}
          .lockup {{ display: flex; align-items: center; gap: 22px; font-size: 72px;
            font-weight: 600; letter-spacing: -.025em; }}
          .lockup svg {{ width: 96px; height: 96px; flex: none; }}
          .mono {{ display: flex; align-items: center; gap: 24px; }}
          .mono svg {{ width: 64px; height: 64px; }}
          .sizes {{ display: flex; align-items: center; gap: 24px; margin-top: 48px; }}
          .sizes svg {{ width: var(--size); height: var(--size); }}
          p {{ margin: 0; color: #89958b; font-size: 22px; letter-spacing: .04em; }}
          .light p {{ color: #58625a; }}
        </style>
        <main>
          <section class="dark">
            <div class="lockup">{mark}<span>Driftwatch</span></div>
            <div class="sizes">{sizes}</div>
            <div class="mono" style="color:#fff">{mono}</div>
            <p>EMERALD PORTAL · ON DARK</p>
          </section>
          <section class="light">
            <div class="lockup">{mark}<span>Driftwatch</span></div>
            <div class="sizes">{sizes}</div>
            <div class="mono" style="color:#151915">{mono}</div>
            <p>EMERALD PORTAL · ON LIGHT</p>
          </section>
        </main>
        """
    )
    page.screenshot(path=str(PREVIEW_DIR / "logo-variants.png"))


def render_illustration_preview(page: Page) -> None:
    cards = []
    for source in sorted(ILLUSTRATION_DIR.glob("*.svg")):
        cards.append(
            f"""
            <article>
              <div class="art">{svg_markup(source)}</div>
              <p>{source.stem}</p>
            </article>
            """
        )
    page.set_viewport_size({"width": 1600, "height": 1200})
    page.set_content(
        f"""
        <style>
          * {{ box-sizing: border-box; }}
          html, body {{ margin: 0; background: #111511; color: #fff;
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif; }}
          main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; padding: 48px; }}
          article {{ overflow: hidden; border: 1px solid #303831; border-radius: 18px;
            background: #f3f5f0; }}
          .art {{ height: 480px; }}
          .art svg {{ width: 100%; height: 100%; display: block; }}
          p {{ margin: 0; padding: 22px 26px; border-top: 1px solid #d8ded5;
            background: #fff; color: #151915; font-size: 24px; font-weight: 650; }}
        </style>
        <main>{"".join(cards)}</main>
        """
    )
    page.screenshot(path=str(PREVIEW_DIR / "empty-state-set.png"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--logo-only", action="store_true", help="Update app icons and logo previews only."
    )
    args = parser.parse_args()
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser: Browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        render_logo_exports(page)
        render_logo_preview(page)
        if not args.logo_only:
            render_illustration_exports(page)
            render_illustration_preview(page)
        browser.close()


if __name__ == "__main__":
    main()
