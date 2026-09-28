"""Screenshot the screening review gate by presenting a completed run as awaiting_review.

Only /api/history and attach responses are rewritten in the browser; every other
non-GET request is aborted. Attach is the same call the UI makes when opening a run. Usage:
  python3 scripts/ux_screening_preview.py <label> [--base URL] [--workflow wf-0001]
"""

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main(label: str, base: str, workflow: str) -> None:
    out = Path("tmp/ux-shots") / label
    out.mkdir(parents=True, exist_ok=True)

    async def rewrite_history(route):
        response = await route.fetch()
        rows = await response.json()
        for row in rows:
            if row.get("workflow_id") == workflow:
                row["status"] = "awaiting_review"
                row["is_completed_hidden"] = False
        await route.fulfill(response=response, body=json.dumps(rows))

    async def rewrite_attach(route):
        response = await route.fetch()
        body = await response.json()
        if isinstance(body, dict) and "status" in body:
            body["status"] = "awaiting_review"
        await route.fulfill(response=response, body=json.dumps(body))

    async def block_writes(route):
        if route.request.method != "GET" and "/api/history/attach" not in route.request.url:
            print(f"blocked {route.request.method} {route.request.url}")
            await route.abort()
        else:
            await route.continue_()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for theme, width in (("dark", 1440), ("light", 1440), ("dark", 390)):
            ctx = await browser.new_context(viewport={"width": width, "height": 900})
            await ctx.add_init_script(f"localStorage.setItem('litreview-theme', '{theme}')")
            await ctx.route("**/api/**", block_writes)
            await ctx.route("**/api/history", rewrite_history)
            await ctx.route("**/api/history/attach*", rewrite_attach)
            page = await ctx.new_page()
            await page.goto(f"{base}/run/{workflow}/review-screening", wait_until="load")
            await page.wait_for_timeout(3000)
            tag = f"{theme}-{width}"
            await page.screenshot(path=str(out / f"{tag}-routed.png"))
            await page.keyboard.press("j")
            await page.keyboard.press("j")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(800)
            await page.screenshot(path=str(out / f"{tag}-expanded.png"))
            print(tag, page.url)
            await ctx.close()
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("--base", default="http://localhost:8001")
    parser.add_argument("--workflow", default="wf-0001")
    args = parser.parse_args()
    asyncio.run(main(args.label, args.base, args.workflow))
