import os
import tempfile
from pathlib import Path
import pytest

from unrar import rarfile

SAMPLE_RAR = Path(__file__).parent.parent / "test_data" / "sample.rar"


@pytest.mark.skipif(not SAMPLE_RAR.exists(), reason="sample.rar not available")
def test_rarfile_imports():
    assert hasattr(rarfile, "RarFile")
    assert hasattr(rarfile, "BadRarFile")
    assert hasattr(rarfile, "RarWrongPassword")


@pytest.mark.skipif(not SAMPLE_RAR.exists(), reason="sample.rar not available")
def test_rarfile_list():
    rf = rarfile.RarFile(SAMPLE_RAR)
    names = rf.namelist()
    assert len(names) > 0
    infos = rf.infolist()
    assert len(infos) == len(names)
    for info in infos:
        assert isinstance(info.filename, str)
        assert info.file_size >= 0


@pytest.mark.skipif(not SAMPLE_RAR.exists(), reason="sample.rar not available")
def test_rarfile_extractall():
    rf = rarfile.RarFile(SAMPLE_RAR)
    with tempfile.TemporaryDirectory() as tmpdir:
        rf.extractall(tmpdir)
        for info in rf.infolist():
            if not info.isdir():
                extracted = Path(tmpdir) / info.filename
                assert extracted.exists()
                assert extracted.stat().st_size == info.file_size


def test_rarfile_bad_archive():
    with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as f:
        f.write(b"not a rar file")
        bad_path = f.name
    try:
        with pytest.raises(rarfile.BadRarFile):
            rarfile.RarFile(bad_path).infolist()
    finally:
        os.unlink(bad_path)
