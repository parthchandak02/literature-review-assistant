"""Capture UX screenshots of the local dashboard for before/after review.

Usage: python3 scripts/ux_screenshots.py <label> [--base http://localhost:8001]
"""

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ROUTES = [
    ("setup", "/"),
    ("activity", "/run/wf-0001"),
    ("results", "/run/wf-0001/results"),
    ("data", "/run/wf-0001/database"),
    ("config", "/run/wf-0001/config"),
    ("cost", "/run/wf-0001/cost"),
    ("cfgready", "/run/wf-0003"),
    ("cfggen", "/run/wf-0002"),
]
MOBILE_ROUTES = [("setup", "/"), ("activity", "/run/wf-0001"), ("results", "/run/wf-0001/results")]


async def capture(page, url: str, path: Path) -> None:
    try:
        await page.goto(url, wait_until="load", timeout=15000)
    except Exception as exc:
        print(f"warn {url}: {exc}")
    await page.wait_for_timeout(2000)
    await page.screenshot(path=str(path))
    print(path)


async def main(label: str, base: str) -> None:
    out = Path("tmp/ux-shots") / label
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for theme in ("dark", "light"):
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme=theme)
            await ctx.add_init_script(f"localStorage.setItem('litreview-theme', '{theme}')")
            page = await ctx.new_page()
            for name, route in ROUTES:
                await capture(page, base + route, out / f"{theme}-{name}.png")
            await ctx.close()
        ctx = await browser.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark")
        page = await ctx.new_page()
        for name, route in MOBILE_ROUTES:
            await capture(page, base + route, out / f"mobile-{name}.png")
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--base", default="http://localhost:8001")
    args = parser.parse_args()
    asyncio.run(main(args.label, args.base))
