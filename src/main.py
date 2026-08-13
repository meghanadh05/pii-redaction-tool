"""Command-line entry point for the phased implementation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from src import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pii-redaction-tool",
        description=(
            "PII Redaction Tool. Phase 1 supplies architecture and tested run-span "
            "primitives; end-to-end redaction is intentionally not enabled yet."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
