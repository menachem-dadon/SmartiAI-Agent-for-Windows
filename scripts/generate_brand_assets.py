"""Render assets/smarti.svg and refresh every shipped Smarti brand asset.

Run from any directory: python scripts/generate_brand_assets.py
Requires Pillow and Playwright with Microsoft Edge installed. Chromium renders
the SVG filters/blend modes; Pillow creates the PNG, Windows ICO and ICNS sizes.
These are development tools only; generated assets are checked into Git.
"""

import base64
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
TAURI_PNGS = {
    "icon.png": 1024,
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
}


def main():
    source = ROOT / "assets/smarti.svg"
    data_url = "data:image/svg+xml;base64," + base64.b64encode(source.read_bytes()).decode("ascii")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 1024}, device_scale_factor=2)
            page.set_content(
                '<style>html,body{margin:0;width:1024px;height:1024px;background:transparent}'
                'img{display:block;width:1024px;height:1024px}</style>'
                f'<img src="{data_url}" alt="">'
            )
            page.locator("img").evaluate("image => image.decode()")
            rendered = page.screenshot(omit_background=True)
        finally:
            browser.close()

    with Image.open(io.BytesIO(rendered)) as screenshot:
        master = screenshot.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    if master.getpixel((0, 0))[3] != 0 or master.getpixel((512, 512))[3] != 255:
        raise RuntimeError("Expected transparent corners and an opaque icon center")

    outputs = {
        ROOT / "assets/logo.png": 1024,
        ROOT / "assets/loading-icon.png.png": 256,
        ROOT / "desktop/public/loading-icon.png": 256,
        ROOT / "desktop/public/loading-icon-dark.png": 256,
    }
    icons = ROOT / "desktop/src-tauri/icons"
    outputs.update({icons / name: size for name, size in TAURI_PNGS.items()})
    for target, size in outputs.items():
        master.resize((size, size), Image.Resampling.LANCZOS).save(target, optimize=True)

    # PNG-compressed 32-bit RGBA frames preserve the rounded transparent corners
    # at Windows tray/taskbar/Explorer sizes, including high-DPI displays.
    ico = io.BytesIO()
    master.save(ico, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    for target in (ROOT / "assets/smarti.ico", icons / "icon.ico", ROOT / "desktop/public/favicon.ico"):
        target.write_bytes(ico.getvalue())
    master.save(icons / "icon.icns", format="ICNS")
    print(f"Generated {len(outputs)} PNGs, 3 ICOs and 1 ICNS from {source.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
