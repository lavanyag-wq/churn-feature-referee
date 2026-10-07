# ADR-001: A third implementation as referee, and where its authority comes from

Status: accepted

## Decision

Every feature has three implementations: the offline batch pipeline, the
serving path, and a referee compiled as directly as possible from the
declared spec, with no shared helpers between the three. Mismatches are
attributed by which side agrees with the referee.

## The alternative

The usual two: trust the offline side by fiat (it is "the source of truth"),
or alert on any two-sided mismatch and let a human attribute it. The first is
how the serving bug ships, because the offline side is wrong often enough
(the leak and tz scenarios here are both offline bugs) that fiat trust
attributes half of all defects to the wrong team. The second is the symmetric
parity check, which cannot attribute at all and sees nothing when both sides
share a bug.

## Why a referee can carry authority

The referee is code, and code is exactly what went wrong on the other two
sides, so its authority has to be argued, not assumed. Three sources. It is
structurally simpler: each feature is a few lines executing the spec's
sentence, with no batching, no state and no shared window helper, so it has
fewer places to be wrong. It is independently derived: written from the spec
text, not from either pipeline, so a bug would have to be invented a third
time rather than inherited. And it is pinned at the boundaries: the test
suite holds hand-computed values for the exact days where every known skew
bug lives (the cutoff day, the window's first day, the day before it, the
never-login user), which is precisely where the other two sides disagree.

When the referee matches neither side, the tool says DIVERGENT and names
nobody (ADR-004), which is the honest behaviour for the case where the
referee's own correctness would be doing the deciding.

## The boundary

The event log is synthetic and the defects are planted, so the numbers here
measure the instrument, not any production system: what transfers is the
attribution machinery and the demonstrated blind spot of two-sided parity,
not the defect rates. The one claim that needs real pipelines is that these
five defect shapes are the common ones; that claim rests on the feature-skew
literature and on experience, and is labelled as such rather than measured.
