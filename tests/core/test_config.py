from pathlib import Path

from fecreator.core.config import get_settings


def test_defaults_bind_localhost(tmp_path: Path) -> None:
    s = get_settings({"FECREATOR_DATA_ROOT": str(tmp_path)})
    assert s.host == "127.0.0.1"
    assert s.port == 8765
    assert s.allow_remote_upload is False
    assert s.data_root == tmp_path


def test_env_overrides(tmp_path: Path) -> None:
    s = get_settings(
        {
            "FECREATOR_DATA_ROOT": str(tmp_path),
            "FECREATOR_PORT": "9000",
            "FECREATOR_ALLOW_REMOTE_UPLOAD": "true",
        }
    )
    assert s.port == 9000
    assert s.allow_remote_upload is True


def test_data_root_required() -> None:
    import pytest

    with pytest.raises(KeyError):
        get_settings({})
