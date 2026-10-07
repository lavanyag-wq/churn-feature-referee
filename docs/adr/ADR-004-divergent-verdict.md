# ADR-004: DIVERGENT is its own verdict and exit code, not a majority vote

Status: accepted

## Decision

When offline, serving and referee all disagree on a pair, the finding is
DIVERGENT, the audit's verdict is UNATTRIBUTED, and the exit code is 2.
The referee's value is reported but no side is named wrong.

## The alternative

Treat the referee as ground truth and attribute both sides as wrong (a
two-against-referee vote already does this for AGREE_WRONG), or pick the
side closest to the referee's value.

## Why not

AGREE_WRONG and DIVERGENT rest on different evidence. In AGREE_WRONG the two
production sides corroborate each other exactly and still differ from the
referee: either both share a bug or the referee is wrong, and the boundary
tests exist to make the second unlikely. In DIVERGENT nothing corroborates
anything: three implementations produced three values, so at least two are
wrong and the referee has even odds of being one of them. Naming a side from
that position converts the tool's one honest "I cannot know" into a guess
wearing the tool's authority. Closeness is worse still: it smuggles in a
metric (closeness in value) that the spec never declared.

Exit 2 exists so a pipeline can page on "something is wrong with the spec or
with all three implementations" without filing it as an ordinary defect. In
the messy scenario, 5 of 600 pairs land there; the right response to those
five is reading the spec, not assigning blame.
