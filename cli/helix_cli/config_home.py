"""Global config directory and env-loading utilities for the Helix CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def get_config_home() -> Path:
    """Return the global Helix config directory, creating it if needed.

    Respects platform conventions:
    - Linux/other: $XDG_CONFIG_HOME/helix or ~/.config/helix
    - macOS: ~/Library/Application Support/helix
    - Windows: %LOCALAPPDATA%/helix or ~/AppData/Local/helix
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    config_dir = base / "helix"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_global_env_path() -> Path:
    """Return the path to the global .env file."""
    return get_config_home() / ".env"


def load_helix_env(workspace: Path | None = None) -> None:
    """Load environment variables from Helix config locations.

    Loading order (later values override earlier):
    1. Global config: ~/.config/helix/.env (or platform equivalent)
    2. Workspace-local: <workspace>/.env (if workspace is provided)

    Shell environment variables always take precedence over .env files
    (handled by python-dotenv's override=False default).
    """
    global_env = get_global_env_path()
    if global_env.is_file():
        load_dotenv(global_env)

    if workspace is not None:
        local_env = Path(workspace) / ".env"
        if local_env.is_file():
            load_dotenv(local_env, override=True)
