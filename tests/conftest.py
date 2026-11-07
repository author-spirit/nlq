import pytest

from nlq import history


@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "PATH", tmp_path / "history.sqlite")
