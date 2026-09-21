"""Where a rule proposed by tool belongs, and the section name the engine reads for it."""

from enum import Enum

class RuleScopeE(str, Enum):
    PERSONAL = "personal"
    SYSTEM = "system"

    def section(self) -> str:
        """The rubric section name the engine reads for this scope."""
        return {RuleScopeE.PERSONAL: "personal rubric", RuleScopeE.SYSTEM: "system"}[self]
