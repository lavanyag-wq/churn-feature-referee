"""Command line interface. The exit code names the attribution outcome.

generate writes the two-commit Delta table. audit runs the offline pipeline,
the serving pipeline and the referee over it under a named scenario, prints
the attribution table, and exits 0 (CLEAN: all three agree everywhere),
1 (DEFECTS: every mismatch attributed to a side), 2 (UNATTRIBUTED: at least
one pair where all three disagree, so no side can be named), or 3 (error).
Scenarios exist so the experiments and the demo can plant known defects; an
audit of a real pair of pipelines is the "clean" scenario applied to real
inputs, where any non-clean finding is news.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import (
    EXIT_CLEAN,
    EXIT_DEFECTS,
    EXIT_ERROR,
    EXIT_UNATTRIBUTED,
    RefereeError,
    UsageError,
)
from .events import generate_events, load_events, read_meta, write_delta
from .offline import OfflinePipeline
from .referee import VERDICT_CLEAN, VERDICT_DEFECTS, AuditReport, attribute, referee_compute
from .serving import ServingPipeline
from .spec import SPECS

SCENARIOS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "clean": (frozenset(), frozenset()),
    "serving_window": (frozenset(), frozenset({"exclusive_window"})),
    "null_bug": (frozenset(), frozenset({"null_default_zero"})),
    "offline_leak": (frozenset({"leak_future"}), frozenset()),
    "offline_tz": (frozenset({"tz_shift"}), frozenset()),
    "shared_window": (frozenset({"exclusive_window"}), frozenset({"exclusive_window"})),
    "messy": (frozenset({"leak_future"}),
              frozenset({"exclusive_window", "null_default_zero"})),
}
# shared_window is the copy-pasted-helper case: the same strict less-than on
# both sides. Offline and serving then agree with each other on every pair,
# the two-sided parity check reports zero mismatches, and only the referee
# can see the pairs that are wrong. The blindspot experiment measures it.


def _cmd_generate(args: argparse.Namespace) -> int:
    events = generate_events(seed=args.seed, n_users=args.users, cutoff_day=args.cutoff)
    meta = write_delta(events, Path(args.out), cutoff_day=args.cutoff)
    print(f"wrote Delta table: {meta['n_snapshot_events']} snapshot events (version 0), "
          f"{meta['n_late_events']} late events (version 1), "
          f"{meta['n_users']} users -> {args.out}")
    return EXIT_CLEAN


def _cmd_audit(args: argparse.Namespace) -> int:
    if args.scenario not in SCENARIOS:
        raise UsageError(f"unknown scenario {args.scenario!r}; "
                         f"choose from {sorted(SCENARIOS)}")
    offline_defects, serving_defects = SCENARIOS[args.scenario]
    table = Path(args.table)
    meta = read_meta(table)
    cutoff = meta["cutoff_day"]
    offline_vals = OfflinePipeline(offline_defects).compute(table, SPECS, cutoff)
    snapshot = load_events(table, version=meta["snapshot_version"])
    serving_vals = ServingPipeline(serving_defects).compute(snapshot, SPECS, cutoff)
    referee_vals = referee_compute(snapshot, SPECS, cutoff)
    report = attribute(offline_vals, serving_vals, referee_vals, cutoff)
    if args.out:
        report.save(Path(args.out))
    print(_summary(report, args.scenario))
    if report.verdict == VERDICT_CLEAN:
        return EXIT_CLEAN
    if report.verdict == VERDICT_DEFECTS:
        return EXIT_DEFECTS
    return EXIT_UNATTRIBUTED


def _summary(report: AuditReport, scenario: str) -> str:
    counts = {k: report.count(k) for k in
              ("SERVING_WRONG", "OFFLINE_WRONG", "AGREE_WRONG", "DIVERGENT")}
    lines = [
        f"scenario: {scenario}",
        f"verdict: {report.verdict}",
        f"pairs audited: {report.n_pairs} ({report.n_users} users x "
        f"{report.n_features} features)",
        f"a two-sided parity check would report: {report.parity_mismatches} mismatches",
        f"actually wrong pairs: {report.wrong_pairs}",
        f"  serving wrong (offline agrees with referee): {counts['SERVING_WRONG']}",
        f"  offline wrong (serving agrees with referee): {counts['OFFLINE_WRONG']}",
        f"  agree but wrong (parity's blind spot):       {counts['AGREE_WRONG']}",
        f"  divergent (no side can be named):            {counts['DIVERGENT']}",
    ]
    for feature, klasses in sorted(report.by_feature().items()):
        detail = ", ".join(f"{k.lower()} {n}" for k, n in sorted(klasses.items()))
        lines.append(f"  {feature}: {detail}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feature-referee",
        description="Training/serving feature parity referee with attribution")
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate", help="write the seeded two-commit Delta table")
    p_gen.add_argument("--seed", type=int, default=11)
    p_gen.add_argument("--users", type=int, default=120)
    p_gen.add_argument("--cutoff", type=int, default=400)
    p_gen.add_argument("--out", required=True)
    p_gen.set_defaults(func=_cmd_generate)

    p_audit = sub.add_parser("audit", help="run all three implementations and attribute")
    p_audit.add_argument("--table", required=True)
    p_audit.add_argument("--scenario", default="clean")
    p_audit.add_argument("--out")
    p_audit.set_defaults(func=_cmd_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RefereeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
