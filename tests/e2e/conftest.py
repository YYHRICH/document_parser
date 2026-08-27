"""Pytest configuration for opt-in, real-parser E2E checks."""

from __future__ import annotations


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "e2e: opt-in real runtime check; set RUN_REAL_PARSER_E2E=1 before running",
    )
