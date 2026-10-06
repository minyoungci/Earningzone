import hashlib
import json
from pathlib import Path
import zipfile
import sys
from types import ModuleType

import pytest

import make_dist
from tossbot.financial_library import DOCUMENT_FILES


def prepare_package(tmp_path, monkeypatch):
    monkeypatch.setattr(make_dist, "ROOT", str(tmp_path))
    monkeypatch.setattr(make_dist, "OUT", str(tmp_path / "app.zip"))
    monkeypatch.setattr(make_dist, "INCLUDE_DIRS", ["tossbot", "web"])
    monkeypatch.setattr(make_dist, "EXTRA_FILES", [".env.example"])
    (tmp_path / "tossbot").mkdir()
    (tmp_path / "tossbot" / "검증.py").write_text("value = 42\n", encoding="utf-8")
    (tmp_path / "tossbot" / ".env").write_text("private", encoding="utf-8")
    (tmp_path / "tossbot" / ".sim_state.json").write_text("private", encoding="utf-8")
    (tmp_path / "web" / "node_modules").mkdir(parents=True)
    (tmp_path / "web" / "node_modules" / "cache.js").write_text("private", encoding="utf-8")
    (tmp_path / ".env.example").write_text("KEY=\n", encoding="utf-8")
    return tmp_path / "app.zip"


def test_zip_is_portable_and_manifest_matches_without_private_files(tmp_path, monkeypatch):
    output = prepare_package(tmp_path, monkeypatch)
    make_dist.main()
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all("\\" not in name for name in archive.namelist())
        manifest = json.loads(archive.read("tossbot-app/BUILD_MANIFEST.json"))
        assert set(manifest["files"]) == {"tossbot/검증.py", ".env.example"}
        for relative, expected in manifest["files"].items():
            content = archive.read("tossbot-app/" + relative)
            assert hashlib.sha256(content).hexdigest() == expected
            assert content == tmp_path.joinpath(relative).read_bytes()
    assert json.loads((tmp_path / "BUILD_MANIFEST.json").read_text(encoding="utf-8")) == manifest


def test_validation_failure_preserves_previous_archive(tmp_path, monkeypatch):
    output = prepare_package(tmp_path, monkeypatch)
    output.write_bytes(b"previous release")
    def fail_validation(self):
        raise zipfile.BadZipFile("verification failed")
    monkeypatch.setattr(zipfile.ZipFile, "testzip", fail_validation)
    with pytest.raises(zipfile.BadZipFile):
        make_dist.main()
    assert output.read_bytes() == b"previous release"


def test_private_material_cannot_ship_even_when_parent_directory_is_selected(tmp_path, monkeypatch):
    output = prepare_package(tmp_path, monkeypatch)
    public = tmp_path / "docs" / "public"
    private = tmp_path / "docs" / "financial"
    public.mkdir(parents=True)
    (private / "images").mkdir(parents=True)
    for name in DOCUMENT_FILES:
        (public / name).write_text("# Public article\n", encoding="utf-8")
    for name in ("docs/financial/source_inventory.json", "docs/financial/images/chart.png",
                 "docs/public/personal.md", "INSIGHTS.md", "discord_private.md"):
        (tmp_path / name).write_text("PRIVATE_SENTINEL", encoding="utf-8")
    monkeypatch.setattr(make_dist, "INCLUDE_DIRS", ["tossbot", "docs"])
    monkeypatch.setattr(make_dist, "EXTRA_FILES", ["INSIGHTS.md", "discord_private.md", "docs/financial/source_inventory.json"])
    make_dist.main()
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        articles = {name.removeprefix("tossbot-app/docs/public/") for name in names if "/docs/public/" in name}
        assert articles == set(DOCUMENT_FILES)
        assert not any("financial/" in name or "discord_" in name or "INSIGHTS" in name for name in names)
        assert all(b"PRIVATE_SENTINEL" not in archive.read(name) for name in names)


def test_zip_defaults_include_only_public_articles():
    assert "docs/financial" not in make_dist.INCLUDE_DIRS
    assert {name for name in make_dist.EXTRA_FILES if name.startswith("docs/")} == make_dist.PUBLIC_FILES
    assert all(make_dist.distributable(name) for name in make_dist.EXTRA_FILES)
    assert not make_dist.distributable("DOCS/FINANCIAL/source.md")
    assert not make_dist.distributable("docs\\financial\\source.md")


def test_desktop_builder_only_bundles_named_public_documents(tmp_path, monkeypatch):
    import build_desktop

    (tmp_path / "web" / "dist").mkdir(parents=True)
    monkeypatch.setattr(build_desktop, "HERE", str(tmp_path))
    captured = []
    package, main = ModuleType("PyInstaller"), ModuleType("PyInstaller.__main__")
    package.__main__ = main
    main.run = lambda args: captured.extend(args)
    monkeypatch.setitem(sys.modules, "PyInstaller", package)
    monkeypatch.setitem(sys.modules, "PyInstaller.__main__", main)
    build_desktop.main()
    datas = [arg for arg in captured if arg.startswith("--add-data=")]
    assert len(datas) == 1 + len(DOCUMENT_FILES)
    assert not any("docs/financial" in arg or "docs\\financial" in arg for arg in datas)
    documents = [arg for arg in datas if arg.endswith("docs/public")]
    assert len(documents) == len(DOCUMENT_FILES)
    assert all("financial" not in arg and arg.endswith("docs/public") for arg in documents)
    assert all(any(name in arg for arg in documents) for name in DOCUMENT_FILES)
