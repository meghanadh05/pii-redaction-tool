"""Command-line entry point for the phased implementation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src import __version__
from src.reporting import detect_docx


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pii-redaction-tool",
        description=(
            "PII Redaction Tool Phase 2A: privacy-safe structured detection and "
            "DOCX extraction. Document redaction is not enabled yet."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    scan_parser = subparsers.add_parser(
        "scan",
        help="scan a DOCX and print a privacy-safe structured detection summary",
    )
    scan_parser.add_argument("input_path", type=Path)
    scan_parser.add_argument(
        "--unsafe-show-pii",
        action="store_true",
        help="include raw detected values in terminal output (unsafe)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "scan":
        report = detect_docx(arguments.input_path)
        print(
            json.dumps(
                report.to_dict(unsafe_show_pii=arguments.unsafe_show_pii),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
