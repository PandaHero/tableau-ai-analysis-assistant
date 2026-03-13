# -*- coding: utf-8 -*-
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from analytics_assistant.src.infra.config import config_loader


@pytest.fixture(autouse=True)
def reset_config_singletons() -> None:
    original_env = os.environ.copy()
    config_loader.AppConfig._instance = None
    config_loader._config_instance = None

    yield

    config_loader.AppConfig._instance = None
    config_loader._config_instance = None
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def repo_root() -> Path:
    base_dir = Path.home() / ".codex" / "memories" / "config-loader-tests"
    base_dir.mkdir(exist_ok=True)
    temp_dir = base_dir / f"config-loader-{uuid4().hex}"
    temp_dir.mkdir()

    yield temp_dir

    shutil.rmtree(temp_dir, ignore_errors=True)


def _write_backend_config(repo_root: Path, content: str) -> Path:
    config_dir = repo_root / "analytics_assistant" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "app.yaml"
    config_path.write_text(content, encoding="utf-8")
    return config_path


def test_app_config_loads_dotenv_before_yaml_expansion(repo_root: Path) -> None:
    config_path = _write_backend_config(
        repo_root,
        """
tableau:
  domain: "${TABLEAU_DOMAIN}"
  site: "${TABLEAU_SITE:-default-site}"
""".strip(),
    )

    (repo_root / ".env").write_text(
        "TABLEAU_DOMAIN=https://root.example.com\nTABLEAU_SITE=root-site\n",
        encoding="utf-8",
    )
    (repo_root / ".env.local").write_text(
        "TABLEAU_DOMAIN=https://root-local.example.com\n",
        encoding="utf-8",
    )
    (repo_root / "analytics_assistant" / ".env").write_text(
        "TABLEAU_DOMAIN=https://package.example.com\n",
        encoding="utf-8",
    )
    (repo_root / "analytics_assistant" / ".env.local").write_text(
        "export TABLEAU_DOMAIN='https://package-local.example.com'\n",
        encoding="utf-8",
    )

    config = config_loader.AppConfig(str(config_path))

    assert config.get_tableau_domain() == "https://package-local.example.com"
    assert config.get_tableau_site() == "root-site"


def test_app_config_keeps_process_env_priority_over_dotenv(repo_root: Path) -> None:
    config_path = _write_backend_config(
        repo_root,
        """
tableau:
  domain: "${TABLEAU_DOMAIN}"
""".strip(),
    )
    (repo_root / ".env").write_text(
        "TABLEAU_DOMAIN=https://dotenv.example.com\n",
        encoding="utf-8",
    )
    os.environ["TABLEAU_DOMAIN"] = "https://process.example.com"

    config = config_loader.AppConfig(str(config_path))

    assert config.get_tableau_domain() == "https://process.example.com"


def test_app_config_reload_refreshes_dotenv_values(repo_root: Path) -> None:
    config_path = _write_backend_config(
        repo_root,
        """
tableau:
  site: "${TABLEAU_SITE:-default-site}"
""".strip(),
    )
    dotenv_path = repo_root / ".env"
    dotenv_path.write_text("TABLEAU_SITE=site-a\n", encoding="utf-8")

    config = config_loader.AppConfig(str(config_path))
    assert config.get_tableau_site() == "site-a"

    dotenv_path.write_text("TABLEAU_SITE=site-b\n", encoding="utf-8")
    config.reload()

    assert config.get_tableau_site() == "site-b"


def test_app_config_accepts_utf8_bom_dotenv(repo_root: Path) -> None:
    config_path = _write_backend_config(
        repo_root,
        """
tableau:
  domain: "${TABLEAU_DOMAIN}"
""".strip(),
    )
    # PowerShell commonly writes UTF-8 with BOM on Windows.
    (repo_root / ".env").write_text(
        "\ufeffTABLEAU_DOMAIN=https://bom.example.com\n",
        encoding="utf-8",
    )

    config = config_loader.AppConfig(str(config_path))

    assert config.get_tableau_domain() == "https://bom.example.com"
