"""Fail a required-check aggregate unless every named validation leg succeeded."""

from __future__ import annotations

import sys


def failed_results(arguments: list[str]) -> list[str]:
    """Return named results that are absent, malformed, or not successful."""
    failures = []
    for argument in arguments:
        name, separator, result = argument.partition("=")
        if not separator or not name or result != "success":
            failures.append(argument)
    return failures


def main(arguments: list[str]) -> int:
    failures = failed_results(arguments)
    if not arguments:
        print("No validation results were supplied.", file=sys.stderr)
        return 1
    if failures:
        print("Required validation did not succeed: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("All required validation legs succeeded: " + ", ".join(arguments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
