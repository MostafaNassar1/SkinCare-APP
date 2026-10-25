from pathlib import Path

import pytest

from skincare_ml import config


def test_default_data_dir_is_outside_onedrive(monkeypatch):
    monkeypatch.delenv("SKINCARE_DATA_DIR", raising=False)

    assert config.data_dir() == Path("C:/SkinCareData").resolve()


def test_data_dir_can_be_moved_with_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))

    assert config.data_dir() == tmp_path.resolve()
    assert config.raw_dir() == tmp_path.resolve() / "starter_kit" / "data" / "raw"
    assert config.prepared_dir() == tmp_path.resolve() / "prepared"


@pytest.mark.parametrize("inside", [".", "ml/data", "backend"])
def test_data_dir_inside_the_repository_is_refused(monkeypatch, inside):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(config.REPO_ROOT / inside))

    with pytest.raises(ValueError, match="inside the repository"):
        config.data_dir()
