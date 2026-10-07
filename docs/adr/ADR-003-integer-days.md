# ADR-003: Integer day numbers instead of datetimes

Status: accepted

## Decision

Event time is an integer day number since an arbitrary epoch. No datetime
objects, no timezone library, anywhere.

## The alternative

Real timestamps with a timezone-aware library, which would look more like
production code.

## Why the boring choice

The defects under study are boundary defects: an event on the cutoff day, an
event on the window's first day, a one-day shift. With integer days every
boundary is exact arithmetic, every test value is computable in one's head,
and no implementation can quietly disagree about what a day is. With real
timestamps the repository would spend its complexity budget on calendar
handling and the boundary cases would depend on the library's conventions,
which is the opposite of a referee whose authority rests on being obviously
correct.

The timezone bug does not disappear with the timezones: tz_shift models a
UTC/local mixup as a one-day shift, which is its observable effect on daily
windows. What is genuinely lost is sub-day semantics (a window ending at a
time of day, DST transitions), and the spec declares day granularity so that
loss is a stated scope, not an accident.
