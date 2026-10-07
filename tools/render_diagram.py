"""Render the architecture diagram to a committed SVG, deterministically.

Generated rather than drawn so a reviewer can regenerate it, committed with
explicit width and height so it renders identically as an img on GitHub, in
an editor preview and offline, and painted on a light background because a
transparent one puts dark labels on a near-black page in dark themes.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "diagram.svg"

W, H = 960, 400
BOX_FILL = "#eef2f7"
BOX_EDGE = "#4a5a6a"
TEXT = "#1d2733"
ACCENT = "#9a3b3b"


def box(x, y, w, h, lines, fill=BOX_FILL):
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" '
        f'fill="{fill}" stroke="{BOX_EDGE}" stroke-width="1.5"/>'
    ]
    line_h = 17
    start = y + h / 2 - line_h * (len(lines) - 1) / 2 + 5
    for i, line in enumerate(lines):
        weight = "bold" if i == 0 else "normal"
        parts.append(
            f'<text x="{x + w / 2}" y="{start + i * line_h}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12.5" '
            f'font-weight="{weight}" fill="{TEXT}">{line}</text>'
        )
    return "".join(parts)


def arrow(x1, y1, x2, y2, label=""):
    parts = [
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{BOX_EDGE}" '
        f'stroke-width="1.5" marker-end="url(#arrow)"/>'
    ]
    if label:
        parts.append(
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 6}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="11" '
            f'fill="{TEXT}">{label}</text>'
        )
    return "".join(parts)


def main() -> None:
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{BOX_EDGE}"/></marker></defs>',
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fcfdfe"/>',
        box(20, 155, 190, 90, ["Delta event table", "commit v0: snapshot", "commit v1: late rows",
                               "+ declared feature spec"]),
        box(280, 45, 200, 72, ["offline pipeline", "time-travels to v0", "batch over the table"]),
        box(280, 165, 200, 72, ["serving pipeline", "per-request, from", "state at the cutoff"]),
        box(280, 285, 200, 72, ["referee", "the spec, executed", "as directly as it reads"]),
        box(550, 155, 160, 90, ["attribution", "per (user, feature):", "who matches whom"]),
        box(770, 35, 170, 64, ["SERVING_WRONG /", "OFFLINE_WRONG", "exit 1: side named"],
            fill="#f7e9e9"),
        box(770, 125, 170, 64, ["AGREE_WRONG", "parity sees nothing;", "the referee does"],
            fill="#f3eedd"),
        box(770, 215, 170, 64, ["DIVERGENT", "all three differ:", "exit 2, no side named"],
            fill="#f3eedd"),
        box(770, 305, 170, 56, ["CLEAN", "all three agree:", "exit 0"]),
        arrow(210, 175, 280, 95, "read v0 (or leak)"),
        arrow(210, 200, 280, 201),
        arrow(210, 225, 280, 310, "same snapshot"),
        arrow(480, 85, 550, 175),
        arrow(480, 201, 550, 200),
        arrow(480, 315, 550, 225),
        arrow(710, 170, 770, 70),
        arrow(710, 190, 770, 157),
        arrow(710, 210, 770, 247),
        arrow(710, 230, 770, 330),
        f'<text x="20" y="25" font-family="Helvetica, Arial, sans-serif" font-size="14" '
        f'font-weight="bold" fill="{ACCENT}">churn-feature-referee: three implementations in, '
        'an attribution out</text>',
        "</svg>",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(svg))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
