"""churn-feature-referee: the parity check that can finally name a side.

A training/serving parity check is symmetric. It can detect that the offline
feature store and the online serving path disagree about a feature value, and
it structurally cannot say which side computed it wrong, no matter how
carefully its diff is read. Worse, when both sides share the same bug (the
usual outcome of a copy-pasted window helper), the parity check reports
nothing at all, because agreement is not correctness. This package adds the
missing instrument: a third implementation of each feature, compiled directly
from the declared spec, used as a referee. Every mismatch is attributed to a
side, and the shared-bug case stops being invisible.
"""

__version__ = "0.1.0"
