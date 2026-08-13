"""Command-line entry point for the phased implementation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from src import __version__
from src.redaction import build_dry_run_report, redact_docx, secret_from_environment
from src.reporting import detect_docx


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pii-redaction-tool",
        description=(
            "Detect PII in DOCX files and replace it with deterministic "
            "synthetic values while preserving Word structure."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    scan_parser = subparsers.add_parser(
        "scan",
        help="scan a DOCX and print a privacy-safe hybrid detection summary",
    )
    scan_parser.add_argument("input_path", type=Path)
    scan_parser.add_argument(
        "--unsafe-show-pii",
        action="store_true",
        help="include raw detected values in terminal output (unsafe)",
    )
    redact_parser = subparsers.add_parser(
        "redact",
        help="redact a DOCX, or preflight without writing with --dry-run",
    )
    redact_parser.add_argument("input_path", type=Path)
    redact_parser.add_argument(
        "--output",
        type=Path,
        help="output DOCX path (required unless --dry-run is used)",
    )
    redact_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="detect, link, pseudonymize, and preflight without writing a DOCX",
    )
    redact_parser.add_argument(
        "--key-env",
        default="PII_REDACTION_KEY",
        help=(
            "environment variable containing at least 16 UTF-8 bytes; required "
            "for writes and optional for dry runs"
        ),
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
    if arguments.command == "redact":
        try:
            secret, key_source = secret_from_environment(
                arguments.key_env,
                required=not arguments.dry_run,
            )
            if arguments.dry_run:
                result = build_dry_run_report(
                    arguments.input_path,
                    secret=secret,
                    key_source=key_source,
                )
            else:
                if arguments.output is None:
                    parser.error("--output is required unless --dry-run is used")
                if secret is None:
                    raise ValueError("A pseudonymization key is required for writing")
                result = redact_docx(
                    arguments.input_path,
                    arguments.output,
                    secret=secret,
                    key_source=key_source,
                )
        except (FileNotFoundError, OSError, ValueError) as error:
            parser.error(str(error))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
