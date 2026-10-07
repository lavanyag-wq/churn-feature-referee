"""Fail the build when a document quotes a figure the code no longer produces.

Loads docs/metrics.json and verifies that each metric's anchor phrase appears,
with the current value substituted in, in every checked document that mentions
that metric at all. Anchors are alternatives: one match is enough, because the
same figure reads differently in a table and in a paragraph. The reverse check
then lists numbers that match no metric, excluding fenced code blocks, inline
code and tables of experiment output, because an example invocation is allowed
to contain a made-up row count.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "docs" / "metrics.json"

# Numbers that legitimately appear with no metric behind them: versions, years,
# ranks, exit codes, alpha levels, section numbers. Kept small and visible.
ALLOWED_BARE = {"0", "1", "2", "3", "7", "30", "90", "400", "371", "999", "100",
                "0.0", "999.0", "2026", "95", "30.5"}


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"<[^>]+>", "", text)  # HTML tags: an img width is not a claim
    return text


def check_document(path: Path, metrics: dict, anchors: dict) -> list[str]:
    failures = []
    raw = path.read_text()
    prose = _strip_code(raw)
    for name, value in metrics.items():
        phrases = [a.format(_fmt(value)) for a in anchors.get(name, [])]
        if not phrases:
            failures.append(f"{path.name}: metric {name} has no anchor phrases (receipts gap)")
            continue
        # A document that never discusses this metric is fine; one that uses an
        # anchor's wording with any value must use the current value.
        number_re = r"-?\d+(?:\.\d+)?"
        stale_patterns = [
            re.compile(re.escape(a).replace(re.escape("{}"), number_re))
            for a in anchors.get(name, [])
        ]
        mentions = any(p.search(prose) for p in stale_patterns)
        if not mentions:
            continue
        if not any(phrase in prose for phrase in phrases):
            failures.append(
                f"{path.name}: {name} is quoted with a stale value "
                f"(expected one of {phrases})"
            )
    return failures


def reverse_check(path: Path, metrics: dict, anchors: dict) -> list[str]:
    prose = _strip_code(path.read_text())
    prose = re.sub(r"\|.*\|", "", prose)  # table rows carry experiment output
    known = {_fmt(v) for v in metrics.values()}
    known |= {_fmt(abs(v)) for v in metrics.values() if isinstance(v, (int, float))}
    unknown = []
    for match in re.finditer(r"(?<![\w.\-/])(\d+(?:\.\d+)?)%?(?![\w.\-/])", prose):
        token = match.group(1)
        if token in known or token in ALLOWED_BARE:
            continue
        unknown.append(token)
    return sorted(set(unknown))


def main() -> int:
    payload = json.loads(METRICS.read_text())
    metrics, anchors = payload["metrics"], payload["anchors"]
    all_failures = []
    for doc in payload["checked_documents"]:
        path = ROOT / doc
        if not path.exists():
            all_failures.append(f"checked document missing: {doc}")
            continue
        all_failures.extend(check_document(path, metrics, anchors))
        bare = reverse_check(path, metrics, anchors)
        if bare:
            print(f"note: {doc} contains numbers nothing re-measures: {bare}")
    if all_failures:
        for failure in all_failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"check_numbers: {len(metrics)} metrics verified across "
          f"{len(payload['checked_documents'])} documents")
    return 0


if __name__ == "__main__":
    sys.exit(main())
