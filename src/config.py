"""Application configuration with privacy-safe defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Paths and operating policy for a redaction run.

    A pseudonymization secret is loaded from an environment variable for any
    future write-enabled run. It is never represented as a checked-in default.
    """

    input_path: Path
    output_path: Path
    unsafe_debug: bool = False
    minimum_confidence: float = 0.50
    pseudonym_key_env: str = "PII_REDACTION_KEY"

    @classmethod
    def for_project_root(cls, project_root: Path) -> "AppConfig":
        return cls(
            input_path=project_root / "input" / "Red Herring Prospectus.docx",
            output_path=project_root
            / "output"
            / "Red Herring Prospectus.redacted.docx",
        )

    def validate_for_redaction(self) -> None:
        """Fail before a run can overwrite or miss its source document."""

        if not self.input_path.is_file():
            raise FileNotFoundError(f"Input DOCX does not exist: {self.input_path}")
        if self.input_path.resolve() == self.output_path.resolve():
            raise ValueError("Input and output paths must be different")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
