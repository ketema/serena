"""
Contract: ProjectLanguageRoutingContract

Defines behavioral contract for mapping file paths to configured project languages.

Component: Project
Purpose: Determine which configured language should handle a given file path
"""

from abc import ABC, abstractmethod

from solidlsp.ls_config import Language


class ProjectLanguageRoutingContract(ABC):
    """
    Behavioral contract for project language routing (sync).

    INVARIANTS:
    - INV-1: Project configuration is not mutated by routing lookup
    - INV-2: No external I/O performed by routing lookup

    PRECONDITIONS:
    - PRE-1: file_path is a non-empty string

    POSTCONDITIONS:
    - POST-1: Returns Language when file_path matches configured language matcher
    - POST-2: Returns None when no configured language matches file_path
    """

    @abstractmethod
    def get_language_for_file(self, file_path: str) -> Language | None:
        """
        Determine language for a file path using configured project languages.

        PRE: file_path is a non-empty string (relative or absolute allowed)

        POST-1: Returns Language if file_path matches a configured language matcher
        POST-2: Returns None if no configured language matches file_path

        INV (5-Point Checklist):
        1. State Invariance: Project config unchanged
        2. Side Effect Prohibition: No I/O
        3. Ordering Constraints: None
        4. Resource Invariants: No file handles opened
        5. Exception Safety: Only ValueError for PRE violation

        ERRORS-1: ValueError if file_path is empty
        """
        ...
