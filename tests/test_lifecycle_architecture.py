"""Regression checks for the DDD dependency direction of source lifecycle."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lifecycle_dependency_direction() -> None:
    domain = (ROOT / "domain" / "lifecycle.py").read_text(encoding="utf-8")
    application = (ROOT / "app" / "source_lifecycle.py").read_text(encoding="utf-8")
    trigger = (ROOT / "trigger" / "cli" / "lifecycle.py").read_text(encoding="utf-8")

    assert "infra" not in domain
    assert "infra" not in application
    assert "._storage" not in application
    assert "document_parser.infra" not in trigger
    assert "build_source_lifecycle" in trigger


def test_infrastructure_implements_lifecycle_ports() -> None:
    adapter = (ROOT / "infra" / "lifecycle" / "filesystem.py").read_text(encoding="utf-8")
    assert "class FileSystemSourceFolder" in adapter
    assert "class JsonSourceLifecycleRepository" in adapter
