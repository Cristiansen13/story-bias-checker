"""Build the Milestone 1 slides as a PDF from their sources in docs/milestone1/presentation/.

usage: python docs/milestone1/build_slides.py   ->   docs/milestone1/milestone1_slides.pdf
Needs playwright, Microsoft Edge and network access for the Google fonts. The speaker notes stay in
the sources (the <aside> of each slide).
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "presentation"
OUT = HERE / "milestone1_slides.pdf"
ARROWS = {"arrow-right": "M0 8H36V0L52 13L36 26V18H0Z", "arrow-left": "M52 8H16V0L0 13L16 26V18H52Z",
          "arrow-down": "M8 0V28H0L13 44L26 28H18V0Z"}
CSS = """
@page { size: 1920px 1080px; margin: 0 }
* { box-sizing: border-box; margin: 0 }
html, body { padding: 0 }
section { position: relative; width: 1920px; height: 1080px; overflow: hidden; break-after: page }
aside { display: none }
ol { padding-left: 40px }
table { width: 100%; border-collapse: collapse }
th, td { padding: 14px 20px; text-align: left; vertical-align: top; border-bottom: 1px solid #D9DEE5 }
"""


def shape(match):
    """The slide format's x-shape arrows, as plain SVG."""
    kind, style = match.group(1), match.group(2)
    width, height = re.search(r"width:(\d+)px;height:(\d+)px", style).groups()
    fill = re.search(r"background:(#\w+)", style).group(1)
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="flex:none">'
            f'<path d="{ARROWS[kind]}" fill="{fill}"/></svg>')


deck = json.loads((SOURCE / "deck.json").read_text("utf-8"))
fonts = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values())
slides = [(SOURCE / "slides" / f"{s}.html").read_text("utf-8") for s in deck["order"]]
body = re.sub(r'<x-shape kind="([\w-]+)" style="([^"]*)"></x-shape>', shape, "\n".join(slides))
page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{deck["title"]}</title>{fonts}'
        f"<style>{CSS}</style></head><body>{body}</body></html>")

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge")
    tab = browser.new_page(viewport={"width": 1920, "height": 1080})
    tab.set_content(page, wait_until="networkidle")
    tab.evaluate("document.fonts.ready")
    tab.pdf(path=str(OUT), prefer_css_page_size=True, print_background=True)
    browser.close()
print(f"wrote {OUT}")
