"""Shared type definitions for type checking.

Uses NewType for IDs to provide compile-time type safety - prevents mixing
different ID types (e.g., passing UserID where NewsletterID expected).

Uses TypeAlias for complex types that are purely structural.
"""

from typing import NewType, TypeAlias

# ID types using NewType for type safety
# These create distinct types that mypy can differentiate
NewsletterID = NewType("NewsletterID", str)
SourceID = NewType("SourceID", str)
UserID = NewType("UserID", str)
RuleID = NewType("RuleID", str)

# Structural aliases using TypeAlias
# These are for complex types where structural compatibility is desired
TopicList: TypeAlias = list[str]
WardNumber: TypeAlias = int  # 1-50
DateString: TypeAlias = str  # ISO 8601 format
BatchID: TypeAlias = str  # YYYY-MM-DD format
