# ADR-002: A two-commit Delta table is the offline source, read by time travel

Status: accepted

## Decision

The event log is a Delta table written in two commits: version 0 holds
exactly the events at or before the label cutoff, version 1 appends the
late-arriving rows. The correct offline pipeline reads version 0 by time
travel; the leak_future defect reads the latest version and anchors windows
at the newest day it can see.

## The alternative

A plain parquet or JSON file per snapshot, which would be simpler and
dependency-free.

## Why Delta

Because the leak being modelled is a Delta-shaped leak. The production
failure this reproduces is a batch job pointed at a table that keeps
receiving appends, computing "the last 30 days" relative to now instead of
relative to the label date. A copied snapshot file cannot express that
failure at all: the snapshot is frozen by construction, so the leak would
have to be simulated by editing data, which proves nothing. With a versioned
table the correct behaviour and the bug are both one line (which version you
open, what you anchor at), and the fix a reader takes away is the real one:
pin the version, anchor at the cutoff.

The cost is two runtime dependencies (deltalake, pyarrow), both pip wheels
with no JVM, and `make verify` stays offline because the table is generated
locally from a seed.

## A consequence worth stating

Version 0 is defined by event time (at or before the cutoff), not by arrival
order: the generator sorts and splits before writing. In production those
differ, and a snapshot taken by commit timestamp can still contain
early-arriving future-dated rows or miss late-arriving past-dated ones. The
tool's point-in-time rule is about event time; mapping it onto a real
table's commit history is the integration work, and it is listed in the
README's future work rather than silently assumed away.
