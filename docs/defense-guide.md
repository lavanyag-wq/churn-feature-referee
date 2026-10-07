# Defense guide: churn-feature-referee

What to say about this repository in an interview, with the command that
proves each claim. Every number here is guarded by `tools/check_numbers.py`,
so if this document and the code ever disagree, the build fails.

## The 30 second version

"Training/serving skew checks have a structural problem: a parity diff is
symmetric, so it can tell you the feature store and the serving path
disagree, but never whose bug it is. And when both sides share a bug, a
copy-pasted window helper, it reports nothing, because they agree on the same
wrong value. I built a referee: a third implementation of each feature
compiled straight from the spec, reading the training side from a Delta
table with time travel for point-in-time correctness. It attributes every
mismatch to a side, and in the shared-bug case where parity reports 0
mismatches, it found the 35 pairs that were wrong."

Then stop. The question that usually comes next is "why should the referee
be trusted over the pipelines", and the answer is ADR-001 in one breath: it
is structurally simpler, independently derived from the spec text, pinned by
hand-computed tests on the exact boundary days where skew bugs live, and
when it matches neither side it names nobody and exits 2.

## The claims, each with how it is proved

### 1. The parity blind spot is real and measured

Command: `python experiments/exp_blindspot.py`

Numbers: with the identical strict less-than planted on both sides, parity
reports 0 mismatches while 35 pairs are wrong across 17 users, 5.8% of all
pairs; sweeping five corpus seeds, the blind spot covers between 3.5% and
6.5% of pairs.

If pushed ("would both sides really share a bug?"): that is the mechanism of
the shared helper, and it is the default outcome of DRY applied across the
batch/serving boundary. The scenario plants the same defect flag on both
pipelines; in the wild it is the same imported function.

### 2. Attribution works when parity can only shrug

Command: `python experiments/exp_attribution.py`

Numbers: on the seeded table of 120 users and 600 pairs, the serving-side
window bug yields 35 mismatched pairs, every one attributed to serving. The
offline as-of-now leak corrupts 248 of the pairs, every one attributed to
offline. The null-default bug hits exactly the 7 never-login users.

If pushed ("248 of 600 seems huge"): the leak moves the window anchor for
every user, so breadth is the expected shape; magnitude is the sharper
story, which is claim 3.

### 3. The leak's magnitude is measured in value units, per feature

Command: `python experiments/exp_leak_magnitude.py`

Numbers: days_since_last_login off by 996 days in the worst case (a
never-login user acquires a login); watch_minutes_7d gains an average of
122.24 minutes of phantom viewing per corrupted pair.

If pushed ("what is the 996?"): the null default is 999, the leaked anchor
puts a post-cutoff login 3 days behind it, and 999 minus 3 is the distance
between "never" and "three days ago", which is exactly the kind of feature
swing that silently reshapes a churn model.

### 4. The numbers cannot silently go stale

Command: `make verify` (or break a README figure and watch the build fail)

`tools/collect_metrics.py` reads the junit XML, the coverage JSON and the
experiment JSON; nothing is typed by hand. `tools/check_numbers.py` matches
anchor phrases, not bare digits, across the README and this document. The
suite is 73 tests at 100% line coverage, and CI re-runs the experiments from
scratch and diffs the regenerated diagram.

## Questions that are meant to be hard

**Isn't the referee just a third place for the same bug?** It can be, which
is why its authority is argued rather than assumed (ADR-001): no shared
helpers, derived from the spec text, boundary-pinned tests. And its failure
mode is contained: if it disagrees with both sides, the tool says DIVERGENT
and names nobody rather than spending the referee's credibility on a guess.

**The events are synthetic. Does any of this transfer?** The defect rates do
not, and the README's "cannot establish" section says so. The instrument
transfers whole: `attribute()` takes three plain dicts, so a real pipeline
pair plus a referee over real labelled semantics plugs in without touching
the machinery. The demonstrated blind spot is structural, not corpus-luck:
two sides sharing a bug agree by construction.

**What is the weakest part?** Equality is exact. Float features computed on
different hardware would need a declared per-feature tolerance, and the spec
has no vocabulary for that yet; today such pairs would show as spurious
mismatches. Second weakest: version 0 is split by event time, which a real
table's commit history does not guarantee (ADR-002 states the gap).

**Why Delta instead of a parquet snapshot?** Because the leak under study is
a versioned-table leak: a frozen file cannot even express "the job read the
unfrozen table", and with versions both the bug and the fix are one line.
The cost is two wheel dependencies and it stays offline.

**Why integer days?** The defects are boundary defects, and the referee's
authority rests on being obviously correct at boundaries; exact day
arithmetic buys that, at the declared cost of sub-day semantics (ADR-003).

**What did you get wrong while building it?** Two things, both in the git
history. A property test caught the generator writing zero-minute
late-arriving watch events, which was understating the leak's damage to
watch_minutes_7d. Then the fix itself shifted the generator's rng stream and
landed while a pinned corpus count was stale, because I chained the test run
and the commit instead of reading the suite green first; the repair commit
names the re-learned rule.

**Couldn't you majority-vote instead of DIVERGENT?** Two-against-one is
already the logic of AGREE_WRONG and of side attribution; when all three
differ there is no majority, only a choice about whose error to trust, and
ADR-004's answer is nobody's. In the messy scenario that is 5 pairs out of
600, and the instruction they carry is "read the spec".

## Things to say and things not to say

Say: "parity is symmetric, so it cannot attribute", "agreement is not
correctness", "the referee names nobody when it matches neither side", "the
defect shapes are claimed as common, the rates here are synthetic".

Do not say: "the referee is ground truth" (its authority is argued and
bounded, ADR-001). Do not quote the 5.8% as a production estimate. Do not
say "Delta Lake at scale" (one local table, two commits, time travel; the
scale story is future work). Do not present the planted defects as found
defects; the find is the instrument's behaviour on them.

## The live demo script

```bash
feature-referee generate --seed 11 --out /tmp/events
feature-referee audit --table /tmp/events --scenario clean ; echo "exit $?"
feature-referee audit --table /tmp/events --scenario serving_window
feature-referee audit --table /tmp/events --scenario shared_window
feature-referee audit --table /tmp/events --scenario messy ; echo "exit $?"
```

The shared_window output is the demo's centre: the line "a two-sided parity
check would report: 0 mismatches" directly above "actually wrong pairs: 35".
