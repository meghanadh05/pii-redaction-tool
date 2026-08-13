from __future__ import annotations

from pathlib import Path

import pytest

from src.config import AppConfig


def test_config_refuses_to_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "source.docx"
    source.touch()
    config = AppConfig(input_path=source, output_path=source)

    with pytest.raises(ValueError, match="must be different"):
        config.validate_for_redaction()
