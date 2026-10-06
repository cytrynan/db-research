import pytest

from dbr.shared.embed.offline import (
    ENV_ONLINE,
    OFFLINE_VARS,
    apply_offline_default,
)


def test_offline_is_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_ONLINE, raising=False)
    for var in OFFLINE_VARS:
        monkeypatch.delenv(var, raising=False)
    assert apply_offline_default() is True
    import os

    assert all(os.environ[var] == "1" for var in OFFLINE_VARS)


def test_online_opt_in_leaves_env_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_ONLINE, "1")
    for var in OFFLINE_VARS:
        monkeypatch.delenv(var, raising=False)
    assert apply_offline_default() is False
    import os

    assert not any(var in os.environ for var in OFFLINE_VARS)


def test_explicit_user_value_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENV_ONLINE, raising=False)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")  # 利用者が明示した値
    apply_offline_default()
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "0"
