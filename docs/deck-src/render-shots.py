"""Render captured terminal output as terminal-style PNGs for the deck."""
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SH = Path(__file__).resolve().parent / "shots"
FONT = "/System/Library/Fonts/Menlo.ttc"
BG = (30, 34, 40)
FG = (220, 224, 228)
PROMPT = (110, 200, 140)
DIM = (140, 150, 160)
OK = (120, 210, 150)
BAD = (230, 120, 110)
KEY = (110, 170, 230)
COMMENT = (150, 160, 170)


def render(name: str, cols: int = 132, size: int = 22, style: str = "terminal", title: str | None = None):
    text = (SH / f"{name}.txt").read_text().rstrip("\n").splitlines()
    font = ImageFont.truetype(FONT, size)
    bold = ImageFont.truetype(FONT, size, index=1) if style == "terminal" else font
    lines = []
    for ln in text:
        wrapped = textwrap.wrap(ln, cols, subsequent_indent="    ", break_long_words=True, break_on_hyphens=False) or [""]
        lines.extend(wrapped)
    cw = font.getlength("M")
    lh = int(size * 1.45)
    pad = int(size * 1.2)
    w = int(cw * cols + 2 * pad)
    h = lh * len(lines) + 2 * pad + int(size * 1.6)
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    # title bar with three dots
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([pad // 2 + i * int(size * 1.1), pad // 2, pad // 2 + i * int(size * 1.1) + int(size * 0.65), pad // 2 + int(size * 0.65)], fill=c)
    if title:
        d.text((w // 2 - font.getlength(title) // 2, pad // 2 - 2), title, font=font, fill=DIM)
    y = pad + int(size * 1.1)
    for ln in lines:
        x = pad
        if style == "terminal" and ln.startswith("$ "):
            d.text((x, y), "$ ", font=bold, fill=PROMPT)
            d.text((x + cw * 2, y), ln[2:], font=bold, fill=FG)
        elif style == "lean":
            color = COMMENT if ln.lstrip().startswith("--") or ln.lstrip().startswith("/--") or ln.lstrip().startswith("`") else FG
            d.text((x, y), ln, font=font, fill=color)
            for kw in ("theorem ", "def ", "by", "have ", "exact ", "unfold ", "intro ", "obtain "):
                idx = ln.find(kw)
                if idx >= 0 and (idx == 0 or ln[idx - 1] == " "):
                    d.text((x + cw * idx, y), kw.rstrip(), font=bold if bold else font, fill=KEY)
        else:
            color = FG
            if "verdict: accept" in ln or ": ok" in ln or ln.strip().endswith("ACCEPT") or "RESULT:" in ln or "  ok  " in ln:
                color = OK
            if "reject" in ln or "MISMATCH" in ln or "BAD" in ln:
                color = BAD
            d.text((x, y), ln, font=font, fill=color)
        y += lh
    out = SH / f"{name}.png"
    img.save(out)
    print(out, img.size)


render("prove", cols=100, size=26, title="prover: llama-receipts (CPU)")
render("verify", cols=132, size=22, title="verifier: verify_trace.py, no model execution")
render("replay", cols=100, size=26, title="verifier: llama-receipts --replay")
render("spec", cols=112, size=24, title="formal spec: spec-check (Lean 4)")
render("lean", cols=112, size=22, style="lean", title="ReceiptsSpec/Quant.lean")
render("zk", cols=100, size=26, title="proof of one node: zk_node.py on Expander")
