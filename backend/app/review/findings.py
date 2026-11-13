"""The common shape of every review finding, whatever produced it (static analysis or AI)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Category(StrEnum):
    BUG = "bug"
    SECURITY = "security"


class Finding(BaseModel, frozen=True):
    path: str  # file path in the pull request's new version
    line: int = Field(ge=1)  # line number in the new file
    severity: Severity
    category: Category
    rule: str  # the tool's rule ID, e.g. "F401" or "B602"
    message: str
    source: Literal["ruff", "bandit"]
