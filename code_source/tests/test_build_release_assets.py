"""Source package of the Windows release: code kept, generated files and tests left out."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_release_assets  # noqa: E402


def _touch(root: Path, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")


def test_stage_source_tree_keeps_code_packages_named_like_excluded_folders(tmp_path: Path) -> None:
    code = tmp_path / "code_source"
    for rel in ("src/server.py", "src/domain/attestation/document.py", "src/exports/presence_sheets.py",
                "attestation/Dupont.pdf", "tests/test_x.py", "src/domain/attestation/__pycache__/document.pyc"):
        _touch(code, rel)

    staged = Path(build_release_assets.stage_source_tree(str(code), str(tmp_path / "stage")))

    assert (staged / "src/server.py").exists()
    assert (staged / "src/domain/attestation/document.py").exists()
    assert (staged / "src/exports/presence_sheets.py").exists()
    assert not (staged / "attestation").exists()
    assert not (staged / "tests").exists()
    assert not (staged / "src/domain/attestation/__pycache__").exists()


def test_release_package_contains_every_src_package() -> None:
    code = Path(__file__).resolve().parents[1]
    packages = {p.parent.relative_to(code) for p in (code / "src").rglob("__init__.py") if "__pycache__" not in p.parts}
    excluded = {p for p in packages
                if any(build_release_assets._is_excluded_dir(part, str(Path(*p.parts[:i])) or ".")
                       for i, part in enumerate(p.parts))}
    assert not excluded, f"src packages left out of the release: {sorted(map(str, excluded))}"
