from __future__ import annotations

from dataclasses import dataclass, field


class ParserUnavailable(RuntimeError):
    """Raised when an optional parser dependency is not available."""


class DocumentParsingError(RuntimeError):
    """Raised when parser execution fails or output is invalid."""


@dataclass
class ParsedDocument:
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
