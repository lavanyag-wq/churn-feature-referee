"""Render the headline charts to committed SVGs, from the experiment JSON.

Data-bound like the prose: the charts read docs/experiments/*.json at render
time, and CI regenerates them and fails on any diff. The first chart's
subject is a zero: the shared-window scenario where parity sees nothing while
35 pairs are wrong, drawn so the nothing is visible.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "docs" / "experiments"
OUT = ROOT / "docs"

INK = "#1d2733"
TEAL = "#2b6777"
WARM = "#9a3b3b"
GOLD = "#b8860b"
BG = "#fcfdfe"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def text(x, y, s, size=12, anchor="middle", fill=INK, weight="normal"):
    return (f'<text x="{x}" y="{y}" {FONT} font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="{fill}">{s}</text>')


def frame(w, h, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">',
            f'<rect width="{w}" height="{h}" fill="{BG}"/>',
            text(w / 2, 26, title, size=15, weight="bold")]


def chart_blindspot() -> None:
    data = json.loads((EXP / "attribution.json").read_text())
    rows = [r for r in data["rows"] if r["scenario"] != "messy"]
    w, h = 860, 350
    left, top, bottom = 70, 60, 78
    px, py = w - left - 30, h - top - bottom
    ymax = max(r["wrong_pairs"] for r in rows) * 1.2

    def sy(v):
        return top + py * (1 - v / ymax)

    svg = frame(w, h, "What the parity diff sees vs what is actually wrong")
    for v in range(0, int(ymax) + 1, 50):
        svg.append(f'<line x1="{left}" y1="{sy(v)}" x2="{w - 30}" y2="{sy(v)}" '
                   f'stroke="#dde5ec"/>')
        svg.append(text(left - 8, sy(v) + 4, str(v), size=11, anchor="end"))
    group = px / len(rows)
    bw = group * 0.3
    for i, r in enumerate(rows):
        cx = left + group * (i + 0.5)
        for dx, value, color in ((-bw * 0.55, r["parity_mismatches"], TEAL),
                                 (bw * 0.55, r["wrong_pairs"], WARM)):
            y = sy(value)
            svg.append(f'<rect x="{cx + dx - bw / 2}" y="{y}" width="{bw}" '
                       f'height="{h - bottom - y}" fill="{color}"/>')
            svg.append(text(cx + dx, y - 6, str(value), size=11, weight="bold"))
        svg.append(text(cx, h - bottom + 16, r["scenario"], size=11))
        svg.append(text(cx, h - bottom + 31, r["verdict"], size=10,
                        fill=TEAL if r["verdict"] == "CLEAN" else WARM))
        if r["scenario"] == "shared_window":
            svg.append(text(cx, top - 6,
                            "the blind spot: parity 0, wrong 35", size=12,
                            fill=WARM, weight="bold"))
            svg.append(f'<rect x="{cx - group * 0.46}" y="{top + 8}" '
                       f'width="{group * 0.92}" height="{h - bottom - top - 8}" '
                       f'fill="none" stroke="{WARM}" stroke-width="1.6" '
                       f'stroke-dasharray="6 4"/>')
    lx = left + 6
    svg.append(f'<rect x="{lx}" y="{top + 2}" width="12" height="12" fill="{TEAL}"/>')
    svg.append(text(lx + 18, top + 12, "parity mismatches (what the diff reports)",
                    anchor="start", size=12))
    svg.append(f'<rect x="{lx}" y="{top + 22}" width="12" height="12" fill="{WARM}"/>')
    svg.append(text(lx + 18, top + 32, "pairs actually wrong vs the spec referee",
                    anchor="start", size=12))
    svg.append(text(left + px / 2, h - 10,
                    f"{data['n_users']} users, 600 user-feature pairs per scenario, "
                    "seeded fixtures", size=12))
    svg.append("</svg>")
    (OUT / "chart-blindspot.svg").write_text("\n".join(svg))


def chart_leak() -> None:
    data = json.loads((EXP / "leak_magnitude.json").read_text())
    rows = data["rows"]
    w, h = 860, 330
    left, top, bottom = 190, 56, 56
    px, py = w - left - 150, h - top - bottom
    xmax = max(r["corrupted_pairs"] for r in rows) * 1.15

    def sx(v):
        return left + px * v / xmax

    svg = frame(w, h, "The as-of-now leak, per feature: pairs corrupted out of 600")
    bh = py / len(rows) * 0.55
    for i, r in enumerate(rows):
        cy = top + py * (i + 0.5) / len(rows)
        svg.append(f'<rect x="{left}" y="{cy - bh / 2}" '
                   f'width="{sx(r["corrupted_pairs"]) - left}" height="{bh}" '
                   f'fill="{TEAL}"/>')
        svg.append(text(left - 8, cy + 4, r["feature"], anchor="end", size=12))
        svg.append(text(sx(r["corrupted_pairs"]) + 8, cy + 1,
                        f"{r['corrupted_pairs']} pairs", anchor="start", size=12,
                        weight="bold"))
        svg.append(text(sx(r["corrupted_pairs"]) + 8, cy + 15,
                        f"worst error {r['worst_abs_error']:g}", anchor="start",
                        size=10.5, fill=WARM))
    svg.append(text(left + px / 2, h - 10,
                    f"total {data['total_corrupted_pairs']} of 600 pairs corrupted "
                    "when offline reads the table as of now instead of the label "
                    "cutoff; worst single error 996 days", size=12))
    svg.append("</svg>")
    (OUT / "chart-leak.svg").write_text("\n".join(svg))


def main() -> None:
    chart_blindspot()
    chart_leak()
    print(f"wrote {OUT / 'chart-blindspot.svg'} and {OUT / 'chart-leak.svg'}")


if __name__ == "__main__":
    main()
