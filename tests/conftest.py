"""Shared pytest configuration."""

import os
from pathlib import Path

import pytest

from synthetic_data import write_base_data, write_manual_data

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR_ENV = "WC2026BET_DATA_DIR"


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Keep `tmp_path` inside the repository unless `--basetemp` says otherwise.

    The system temp directory sits on a small drive on the development machine.
    pytest wipes the base directory at the start of every run, so scratch output
    does not accumulate.
    """

    if config.option.basetemp is None:
        scratch = REPO_ROOT / ".test-artifacts"
        scratch.mkdir(exist_ok=True)  # pytest creates the base directory but not its parent
        config.option.basetemp = str(scratch / "pytest")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `real_data` tests unless the environment names a directory with the real snapshots."""

    if os.environ.get(DATA_DIR_ENV):
        return
    skip = pytest.mark.skip(reason=f"real snapshots not available: set {DATA_DIR_ENV}")
    for item in items:
        if "real_data" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def real_data_dir() -> Path:
    """Directory holding the real `base-data/` and `data/manual/` snapshots."""

    value = os.environ.get(DATA_DIR_ENV)
    if not value:
        pytest.fail(f"Tests that use real snapshots need the real_data marker and {DATA_DIR_ENV}")
    data_dir = Path(value)
    missing = [name for name in ("base-data", "data/manual") if not (data_dir / name).is_dir()]
    if missing:
        pytest.fail(f"{DATA_DIR_ENV}={data_dir} lacks: {', '.join(missing)}")
    return data_dir


@pytest.fixture(scope="session")
def real_base_data(real_data_dir: Path) -> Path:
    return real_data_dir / "base-data"


@pytest.fixture(scope="session")
def real_manual_data(real_data_dir: Path) -> Path:
    return real_data_dir / "data" / "manual"


@pytest.fixture(scope="session")
def synthetic_base_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_base_data(tmp_path_factory.mktemp("synthetic") / "base-data")


@pytest.fixture(scope="session")
def synthetic_manual_data(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write_manual_data(tmp_path_factory.mktemp("synthetic-manual") / "manual")


@pytest.fixture(params=["synthetic", pytest.param("real", marks=pytest.mark.real_data)])
def base_data(request: pytest.FixtureRequest) -> Path:
    """Either snapshot set, for invariants that must hold on both."""

    path: Path = request.getfixturevalue(f"{request.param}_base_data")
    return path
