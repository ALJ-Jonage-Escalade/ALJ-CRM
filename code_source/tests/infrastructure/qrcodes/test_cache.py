"""Tests of the local WhatsApp QRCode generation and its disk cache."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

import paths
from infrastructure.qrcodes import cache
from infrastructure.qrcodes import find_group_qrcode, get_group_qrcode, qrcode_cache_dir, qrcode_filename

LINK = "https://chat.whatsapp.com/exemple"


@pytest.fixture
def root_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(paths, "ROOT_DIR", str(tmp_path))
    return tmp_path


def test_get_group_qrcode_generates_png_in_exports(root_dir: Path) -> None:
    from PIL import Image

    path = get_group_qrcode(LINK, "Loisir / cours")
    assert path == str(root_dir / "exports" / "qrcodes" / "QRCode_WhatsApp_Loisir  cours.png")
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    with Image.open(path) as img:
        assert img.width == img.height
    assert os.listdir(root_dir / "exports" / "qrcodes") == ["QRCode_WhatsApp_Loisir  cours.png"]


def test_get_group_qrcode_reuses_cached_file(root_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_group_qrcode(LINK, "Loisir")
    calls: list[str] = []
    monkeypatch.setattr(cache.segno, "make", lambda *args, **kwargs: calls.append("make"))
    assert get_group_qrcode(LINK, "Loisir") == first
    assert calls == []


def test_get_group_qrcode_force_regenerates(root_dir: Path) -> None:
    path = get_group_qrcode(LINK, "Loisir")
    assert path is not None
    Path(path).write_bytes(b"stale")
    assert get_group_qrcode(LINK, "Loisir", force=True) == path
    assert Path(path).read_bytes().startswith(b"\x89PNG")


def test_qrcode_cache_dir_falls_back_to_temp_when_root_unwritable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A regular file as ROOT_DIR makes os.makedirs fail on every OS
    unwritable_root = tmp_path / "not_a_dir"
    unwritable_root.write_text("")
    monkeypatch.setattr(paths, "ROOT_DIR", str(unwritable_root))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    assert qrcode_cache_dir() == str(tmp_path / "tmp" / "alj_qrcodes")
    path = get_group_qrcode(LINK, "Loisir")
    assert path == str(tmp_path / "tmp" / "alj_qrcodes" / "QRCode_WhatsApp_Loisir.png")
    assert find_group_qrcode(None, "Inconnu", "Loisir") == path


@pytest.mark.parametrize(("link", "group_name"), [("", "Loisir"), ("   ", "Loisir"), (LINK, ""), (LINK, "///")])
def test_get_group_qrcode_missing_input_returns_none(root_dir: Path, link: str, group_name: str) -> None:
    assert get_group_qrcode(link, group_name) is None


def test_find_group_qrcode_none_when_not_cached(root_dir: Path) -> None:
    assert find_group_qrcode("Loisir", None, "") is None


def test_qrcode_filename_sanitises_group_name() -> None:
    assert qrcode_filename("Compétition - U15/U19") == "QRCode_WhatsApp_Compétition - U15U19.png"
    assert qrcode_filename("?!") is None
