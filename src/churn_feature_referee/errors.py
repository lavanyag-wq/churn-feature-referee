"""Error types and exit codes: "attributed" and "cannot attribute" are different.

EXIT_CLEAN means all three implementations agree everywhere. EXIT_DEFECTS
means mismatches were found and every one was attributed to a side (serving,
offline, or both). EXIT_UNATTRIBUTED means at least one pair where all three
values differ, so the referee can prove something is wrong but cannot name a
single side; that case is its own outcome because a pipeline should page on
it rather than file it under either verdict. EXIT_ERROR means the tool failed
to answer at all.
"""

from __future__ import annotations

EXIT_CLEAN = 0
EXIT_DEFECTS = 1
EXIT_UNATTRIBUTED = 2
EXIT_ERROR = 3


class RefereeError(Exception):
    """Base error. Maps to EXIT_ERROR at the CLI boundary."""


class UsageError(RefereeError):
    """The caller asked for something invalid; refused before any work starts."""


class DataError(RefereeError):
    """An input table or file is missing, malformed, or inconsistent."""
