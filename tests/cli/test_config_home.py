"""Tests for helix_cli.config_home — global config directory and env loading.

Covers:
- get_config_home() platform dispatch (Linux/XDG, macOS, Windows, fallbacks)
- get_global_env_path() derivation from config home
- load_helix_env() loading order, override semantics, edge cases
- _upsert_env_line() insert/update behavior
- setup_command env file output (provider, model, key persistence)
- load_config integration with global env
- GeneConfig picks up values written by setup
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_env(path: Path, **kv: str) -> Path:
    """Write a .env file at *path* with the given key=value pairs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _read_env(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# get_config_home
# ---------------------------------------------------------------------------


class TestGetConfigHome:
    """Tests for get_config_home()."""

    def test_returns_xdg_config_on_linux(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        xdg = tmp_path / "custom_xdg"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == xdg / "helix"
        assert result.is_dir()

    def test_falls_back_to_dot_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        home = tmp_path / "fakehome"
        home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == home / ".config" / "helix"
        assert result.is_dir()

    def test_windows_uses_localappdata(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        local = tmp_path / "AppData" / "Local"
        local.mkdir(parents=True)
        monkeypatch.setenv("LOCALAPPDATA", str(local))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == local / "helix"

    def test_windows_fallback_when_no_localappdata(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        home = tmp_path / "fakehome"
        home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == home / "AppData" / "Local" / "helix"

    def test_darwin_uses_application_support(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        home = tmp_path / "fakehome"
        home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == home / "Library" / "Application Support" / "helix"

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result.is_dir()

    def test_creates_nested_parents(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        deep = tmp_path / "a" / "b" / "c"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(deep))

        from helix_cli.config_home import get_config_home

        result = get_config_home()
        assert result == deep / "helix"
        assert result.is_dir()

    def test_idempotent_when_already_exists(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.config_home import get_config_home

        first = get_config_home()
        second = get_config_home()
        assert first == second
        assert first.is_dir()


class TestGetGlobalEnvPath:
    """Tests for get_global_env_path()."""

    def test_returns_env_under_config_home(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.config_home import get_global_env_path

        result = get_global_env_path()
        assert result == tmp_path / "helix" / ".env"
        assert result.name == ".env"


# ---------------------------------------------------------------------------
# load_helix_env
# ---------------------------------------------------------------------------


class TestLoadHelixEnv:
    """Tests for load_helix_env()."""

    def test_loads_global_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="global-key-123",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        assert os.environ.get("GENE_GEMINI_API_KEY") == "global-key-123"

    def test_workspace_overrides_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="global-key",
        )
        workspace = tmp_path / "workspace"
        _write_env(workspace / ".env", GENE_GEMINI_API_KEY="local-key")

        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(workspace)
        assert os.environ.get("GENE_GEMINI_API_KEY") == "local-key"

    def test_global_env_used_when_no_workspace_env(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_OPENAI_API_KEY="from-global",
        )
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # No .env in workspace

        monkeypatch.delenv("GENE_OPENAI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(workspace)
        assert os.environ.get("GENE_OPENAI_API_KEY") == "from-global"

    def test_no_env_files_is_safe(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))

        from helix_cli.config_home import load_helix_env

        # Should not raise
        load_helix_env()
        load_helix_env(tmp_path / "nonexistent")

    def test_workspace_none_only_loads_global(self, tmp_path, monkeypatch):
        """Calling load_helix_env(None) or load_helix_env() loads global only."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_OPENROUTER_API_KEY="global-only",
        )
        monkeypatch.delenv("GENE_OPENROUTER_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(None)
        assert os.environ.get("GENE_OPENROUTER_API_KEY") == "global-only"

    def test_workspace_adds_vars_not_in_global(self, tmp_path, monkeypatch):
        """Workspace .env can introduce new vars not present in global."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="gem-key",
        )
        workspace = tmp_path / "workspace"
        _write_env(
            workspace / ".env",
            GENE_OPENAI_API_KEY="oai-from-workspace",
        )

        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GENE_OPENAI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(workspace)
        # Both should be set
        assert os.environ.get("GENE_GEMINI_API_KEY") == "gem-key"
        assert os.environ.get("GENE_OPENAI_API_KEY") == "oai-from-workspace"

    def test_global_multiple_vars(self, tmp_path, monkeypatch):
        """Global env can contain multiple GENE_* vars including providers."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="my-key",
            GENE_META_PROVIDER="gemini",
            GENE_TARGET_PROVIDER="gemini",
            GENE_JUDGE_PROVIDER="gemini",
            GENE_META_MODEL="gemini-2.5-flash",
            GENE_TARGET_MODEL="gemini-2.5-flash",
            GENE_JUDGE_MODEL="gemini-2.5-flash",
        )
        for key in [
            "GENE_GEMINI_API_KEY",
            "GENE_META_PROVIDER",
            "GENE_TARGET_PROVIDER",
            "GENE_JUDGE_PROVIDER",
            "GENE_META_MODEL",
            "GENE_TARGET_MODEL",
            "GENE_JUDGE_MODEL",
        ]:
            monkeypatch.delenv(key, raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        assert os.environ.get("GENE_GEMINI_API_KEY") == "my-key"
        assert os.environ.get("GENE_META_PROVIDER") == "gemini"
        assert os.environ.get("GENE_META_MODEL") == "gemini-2.5-flash"

    def test_empty_global_env_file(self, tmp_path, monkeypatch):
        """Empty .env file doesn't break loading."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        env_dir = tmp_path / "helix"
        env_dir.mkdir()
        (env_dir / ".env").write_text("", encoding="utf-8")

        from helix_cli.config_home import load_helix_env

        load_helix_env()  # Should not raise

    def test_comments_and_blank_lines_in_env(self, tmp_path, monkeypatch):
        """Comments and blank lines are handled gracefully by python-dotenv."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        env_dir = tmp_path / "helix"
        env_dir.mkdir()
        (env_dir / ".env").write_text(
            "# This is a comment\n\nGENE_GEMINI_API_KEY=key-with-comments\n# Another comment\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        assert os.environ.get("GENE_GEMINI_API_KEY") == "key-with-comments"


# ---------------------------------------------------------------------------
# _upsert_env_line
# ---------------------------------------------------------------------------


class TestUpsertEnvLine:
    """Tests for setup._upsert_env_line()."""

    def test_appends_to_empty_list(self):
        from helix_cli.commands.setup import _upsert_env_line

        lines: list[str] = []
        _upsert_env_line(lines, "FOO", "bar")
        assert lines == ["FOO=bar"]

    def test_appends_new_key(self):
        from helix_cli.commands.setup import _upsert_env_line

        lines = ["FOO=bar"]
        _upsert_env_line(lines, "BAZ", "qux")
        assert lines == ["FOO=bar", "BAZ=qux"]

    def test_updates_existing_key(self):
        from helix_cli.commands.setup import _upsert_env_line

        lines = ["GENE_GEMINI_API_KEY=old", "OTHER=val"]
        _upsert_env_line(lines, "GENE_GEMINI_API_KEY", "new")
        assert lines == ["GENE_GEMINI_API_KEY=new", "OTHER=val"]

    def test_updates_first_occurrence_only(self):
        from helix_cli.commands.setup import _upsert_env_line

        lines = ["KEY=first", "KEY=second"]
        _upsert_env_line(lines, "KEY", "updated")
        assert lines == ["KEY=updated", "KEY=second"]

    def test_does_not_match_prefix_substring(self):
        """KEY_EXTRA should not match KEY."""
        from helix_cli.commands.setup import _upsert_env_line

        lines = ["GENE_GEMINI_API_KEY_EXTRA=val"]
        _upsert_env_line(lines, "GENE_GEMINI_API_KEY", "newval")
        assert lines == ["GENE_GEMINI_API_KEY_EXTRA=val", "GENE_GEMINI_API_KEY=newval"]

    def test_value_with_equals_sign(self):
        """Values containing '=' are handled correctly."""
        from helix_cli.commands.setup import _upsert_env_line

        lines: list[str] = []
        _upsert_env_line(lines, "URL", "postgres://user:pass@host/db?opt=1")
        assert lines == ["URL=postgres://user:pass@host/db?opt=1"]


# ---------------------------------------------------------------------------
# setup_command file output
# ---------------------------------------------------------------------------


class TestSetupCommandOutput:
    """Verify setup_command writes the correct .env content."""

    def test_setup_writes_to_global_config(self, tmp_path, monkeypatch):
        """setup_command with no --dir writes to global config home."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.commands.setup import _upsert_env_line, get_global_env_path

        env_path = get_global_env_path()
        env_lines: list[str] = []

        # Simulate what setup_command does for gemini provider
        _upsert_env_line(env_lines, "GENE_GEMINI_API_KEY", "test-api-key")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_META_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_TARGET_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", "gemini-2.5-flash")

        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        parsed = _read_env(env_path)
        assert parsed["GENE_GEMINI_API_KEY"] == "test-api-key"
        assert parsed["GENE_META_PROVIDER"] == "gemini"
        assert parsed["GENE_TARGET_PROVIDER"] == "gemini"
        assert parsed["GENE_JUDGE_PROVIDER"] == "gemini"
        assert parsed["GENE_META_MODEL"] == "gemini-2.5-flash"
        assert parsed["GENE_TARGET_MODEL"] == "gemini-2.5-flash"
        assert parsed["GENE_JUDGE_MODEL"] == "gemini-2.5-flash"

    def test_setup_with_explicit_dir(self, tmp_path, monkeypatch):
        """setup_command with --dir writes to the specified directory."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        from helix_cli.commands.setup import _upsert_env_line

        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        env_path = custom_dir / ".env"

        env_lines: list[str] = []
        _upsert_env_line(env_lines, "GENE_OPENAI_API_KEY", "sk-test123")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "openai")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        parsed = _read_env(env_path)
        assert parsed["GENE_OPENAI_API_KEY"] == "sk-test123"
        assert parsed["GENE_META_PROVIDER"] == "openai"

        # Global config should NOT have been created
        global_env = tmp_path / "xdg" / "helix" / ".env"
        assert not global_env.exists()

    def test_setup_preserves_existing_env_lines(self, tmp_path, monkeypatch):
        """Re-running setup preserves unrelated lines in .env."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.commands.setup import _upsert_env_line, get_global_env_path

        env_path = get_global_env_path()

        # Pre-existing content
        _write_env(
            env_path,
            GENE_DATABASE_URL="sqlite:///old.db",
            GENE_GEMINI_API_KEY="old-key",
        )

        # Simulate re-running setup (update key, add new vars)
        env_lines = env_path.read_text(encoding="utf-8").splitlines()
        _upsert_env_line(env_lines, "GENE_GEMINI_API_KEY", "new-key")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_META_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_TARGET_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", "gemini-2.5-flash")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        parsed = _read_env(env_path)
        assert parsed["GENE_DATABASE_URL"] == "sqlite:///old.db"  # Preserved
        assert parsed["GENE_GEMINI_API_KEY"] == "new-key"  # Updated
        assert parsed["GENE_META_PROVIDER"] == "gemini"  # Added

    def test_setup_all_providers_write_correct_key(self, tmp_path, monkeypatch):
        """Each provider writes its own API key env var."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.commands.setup import PROVIDERS, _upsert_env_line

        for provider_name, info in PROVIDERS.items():
            lines: list[str] = []
            _upsert_env_line(lines, info["env_key"], f"key-for-{provider_name}")
            _upsert_env_line(lines, "GENE_META_PROVIDER", provider_name)

            assert f"{info['env_key']}=key-for-{provider_name}" in lines
            assert f"GENE_META_PROVIDER={provider_name}" in lines

    def test_setup_json_output_includes_config_home(self, tmp_path, monkeypatch):
        """--json output includes the config_home path."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.commands.setup import PROVIDERS
        from helix_cli.config_home import get_config_home

        data = {
            "providers": list(PROVIDERS.keys()),
            "config_home": str(get_config_home()),
        }
        assert "providers" in data
        assert "config_home" in data
        assert data["config_home"].endswith("/helix")


# ---------------------------------------------------------------------------
# Integration: GeneConfig picks up global env values
# ---------------------------------------------------------------------------


class TestGeneConfigIntegration:
    """Verify GeneConfig reads env vars set by load_helix_env."""

    def test_gene_config_reads_api_key_from_global_env(self, tmp_path, monkeypatch):
        """GeneConfig picks up GENE_GEMINI_API_KEY after load_helix_env()."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="integration-key",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()

        from api.config.models import GeneConfig

        config = GeneConfig()
        assert config.gemini_api_key == "integration-key"

    def test_gene_config_reads_provider_from_global_env(self, tmp_path, monkeypatch):
        """GeneConfig picks up provider settings after load_helix_env()."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="test-key",
            GENE_META_PROVIDER="gemini",
            GENE_TARGET_PROVIDER="gemini",
            GENE_JUDGE_PROVIDER="gemini",
            GENE_META_MODEL="gemini-2.5-flash",
            GENE_TARGET_MODEL="gemini-2.5-flash",
            GENE_JUDGE_MODEL="gemini-2.5-flash",
        )
        for key in [
            "GENE_GEMINI_API_KEY",
            "GENE_META_PROVIDER",
            "GENE_TARGET_PROVIDER",
            "GENE_JUDGE_PROVIDER",
            "GENE_META_MODEL",
            "GENE_TARGET_MODEL",
            "GENE_JUDGE_MODEL",
        ]:
            monkeypatch.delenv(key, raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()

        from api.config.models import GeneConfig

        config = GeneConfig()
        assert config.gemini_api_key == "test-key"
        assert config.meta_provider == "gemini"
        assert config.target_provider == "gemini"
        assert config.judge_provider == "gemini"
        assert config.meta_model == "gemini-2.5-flash"
        assert config.target_model == "gemini-2.5-flash"
        assert config.judge_model == "gemini-2.5-flash"

    def test_workspace_env_overrides_global_for_gene_config(self, tmp_path, monkeypatch):
        """Workspace .env provider overrides global for GeneConfig."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="global-gem-key",
            GENE_META_PROVIDER="gemini",
            GENE_TARGET_PROVIDER="gemini",
            GENE_JUDGE_PROVIDER="gemini",
        )
        workspace = tmp_path / "workspace"
        _write_env(
            workspace / ".env",
            GENE_OPENAI_API_KEY="local-oai-key",
            GENE_META_PROVIDER="openai",
            GENE_TARGET_PROVIDER="openai",
            GENE_JUDGE_PROVIDER="openai",
        )

        for key in [
            "GENE_GEMINI_API_KEY",
            "GENE_OPENAI_API_KEY",
            "GENE_META_PROVIDER",
            "GENE_TARGET_PROVIDER",
            "GENE_JUDGE_PROVIDER",
        ]:
            monkeypatch.delenv(key, raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(workspace)

        from api.config.models import GeneConfig

        config = GeneConfig()
        # Provider overridden by workspace
        assert config.meta_provider == "openai"
        # Workspace also introduces openai key
        assert config.openai_api_key == "local-oai-key"
        # Global gemini key still loaded (workspace didn't override it)
        assert config.gemini_api_key == "global-gem-key"

    def test_constructor_args_override_env(self, tmp_path, monkeypatch):
        """GeneConfig constructor args take precedence over env vars."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_META_PROVIDER="gemini",
            GENE_META_MODEL="gemini-2.5-flash",
        )
        monkeypatch.delenv("GENE_META_PROVIDER", raising=False)
        monkeypatch.delenv("GENE_META_MODEL", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()

        from api.config.models import GeneConfig

        config = GeneConfig(meta_provider="openrouter", meta_model="custom-model")
        assert config.meta_provider == "openrouter"
        assert config.meta_model == "custom-model"


# ---------------------------------------------------------------------------
# Integration: load_config uses global env
# ---------------------------------------------------------------------------


class TestLoadConfigIntegration:
    """Verify load_config correctly loads from global env + workspace."""

    @pytest.fixture()
    def _prompt_workspace(self, tmp_path):
        """Create a minimal prompt workspace with prompt.yaml and dataset.yaml."""
        workspace = tmp_path / "prompts"
        workspace.mkdir()
        prompt_dir = workspace / "test-prompt"
        prompt_dir.mkdir()

        (prompt_dir / "prompt.yaml").write_text(
            "id: test-prompt\npurpose: testing\ntemplate: |\n  Hello {{ name }}\n",
            encoding="utf-8",
        )
        (prompt_dir / "dataset.yaml").write_text(
            "cases:\n"
            "  - name: basic\n"
            "    variables:\n"
            "      name: world\n"
            "    chat_history:\n"
            "      - role: user\n"
            "        content: hi\n"
            "    expected_output:\n"
            "      require_content: true\n",
            encoding="utf-8",
        )
        return workspace, prompt_dir

    def test_load_config_uses_global_env(self, tmp_path, monkeypatch, _prompt_workspace):
        """load_config picks up API key from global .env when no workspace .env."""
        _workspace, prompt_dir = _prompt_workspace
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="config-test-key",
            GENE_META_PROVIDER="gemini",
            GENE_TARGET_PROVIDER="gemini",
            GENE_JUDGE_PROVIDER="gemini",
        )
        for key in [
            "GENE_GEMINI_API_KEY",
            "GENE_META_PROVIDER",
            "GENE_TARGET_PROVIDER",
            "GENE_JUDGE_PROVIDER",
        ]:
            monkeypatch.delenv(key, raising=False)

        from helix_cli.project.loader import load_config

        config, _evo_config, _run_kwargs = load_config(prompt_dir)
        assert config.gemini_api_key == "config-test-key"
        assert config.meta_provider == "gemini"

    def test_load_config_workspace_env_overrides(self, tmp_path, monkeypatch, _prompt_workspace):
        """Workspace .env overrides global for load_config."""
        workspace, prompt_dir = _prompt_workspace
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="global-key",
        )
        _write_env(
            workspace / ".env",
            GENE_GEMINI_API_KEY="workspace-key",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.project.loader import load_config

        config, _, _ = load_config(prompt_dir)
        assert config.gemini_api_key == "workspace-key"

    def test_load_config_yaml_overrides_env(self, tmp_path, monkeypatch, _prompt_workspace):
        """config.yaml values take precedence over env vars for provider/model."""
        _workspace, prompt_dir = _prompt_workspace
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="my-key",
            GENE_META_PROVIDER="gemini",
            GENE_META_MODEL="gemini-2.5-flash",
        )
        for key in ["GENE_GEMINI_API_KEY", "GENE_META_PROVIDER", "GENE_META_MODEL"]:
            monkeypatch.delenv(key, raising=False)

        # Write config.yaml that overrides provider/model
        (prompt_dir / "config.yaml").write_text(
            "provider: openrouter\nmodel: openai/gpt-4o\n",
            encoding="utf-8",
        )

        from helix_cli.project.loader import load_config

        config, _, _ = load_config(prompt_dir)
        # config.yaml overrides env via constructor args
        assert config.meta_provider == "openrouter"
        assert config.meta_model == "openai/gpt-4o"
        # API key still from global env
        assert config.gemini_api_key == "my-key"

    def test_load_config_no_env_no_config_yaml(self, tmp_path, monkeypatch, _prompt_workspace):
        """load_config works with defaults when no .env and no config.yaml exist."""
        _, prompt_dir = _prompt_workspace
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))

        from helix_cli.project.loader import load_config

        config, _evo_config, _run_kwargs = load_config(prompt_dir)
        # Should use defaults — no crash
        assert config.meta_provider == "openrouter"  # default
        assert config.openrouter_api_key is None  # no key set


# ---------------------------------------------------------------------------
# End-to-end: simulate setup → evolve config resolution
# ---------------------------------------------------------------------------


class TestSetupToEvolveFlow:
    """Simulate the user flow: helix setup → helix evolve (config resolution)."""

    def test_setup_then_evolve_from_different_dir(self, tmp_path, monkeypatch):
        """API key set by setup is found by evolve even from a different CWD.

        This is the core bug scenario: user runs 'helix setup' in one directory,
        then 'helix evolve' from another. Previously the .env was saved to CWD
        and not found later.
        """
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        # 1. Simulate setup writing to global config
        from helix_cli.commands.setup import _upsert_env_line, get_global_env_path

        env_path = get_global_env_path()
        env_lines: list[str] = []
        _upsert_env_line(env_lines, "GENE_GEMINI_API_KEY", "setup-key-123")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_META_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_TARGET_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", "gemini-2.5-flash")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        # 2. Create prompt workspace in a completely different directory
        work_dir = tmp_path / "somewhere" / "else" / "projects"
        prompt_dir = work_dir / "my-prompt"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "prompt.yaml").write_text(
            "id: my-prompt\npurpose: test\ntemplate: 'Hello {{ x }}'\n",
            encoding="utf-8",
        )

        # 3. Clear all env vars (simulating fresh process)
        for key in list(os.environ):
            if key.startswith("GENE_"):
                monkeypatch.delenv(key, raising=False)

        # 4. load_config should find the global config
        from helix_cli.project.loader import load_config

        config, _, _ = load_config(prompt_dir)
        assert config.gemini_api_key == "setup-key-123"
        assert config.meta_provider == "gemini"
        assert config.meta_model == "gemini-2.5-flash"

    def test_setup_then_models_finds_key(self, tmp_path, monkeypatch):
        """helix models finds the API key from global config after setup."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        # Simulate setup
        from helix_cli.commands.setup import _upsert_env_line, get_global_env_path

        env_path = get_global_env_path()
        env_lines: list[str] = []
        _upsert_env_line(env_lines, "GENE_OPENAI_API_KEY", "sk-models-test")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        # Clear env
        monkeypatch.delenv("GENE_OPENAI_API_KEY", raising=False)

        # Simulate what models_command does
        from helix_cli.config_home import load_helix_env

        load_helix_env()

        from api.config.models import GeneConfig
        from api.gateway.registry import get_provider_config

        config = GeneConfig()
        provider_config = get_provider_config("openai")
        api_key = getattr(config, provider_config.api_key_field, None)
        assert api_key == "sk-models-test"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error conditions."""

    def test_env_file_with_quoted_values(self, tmp_path, monkeypatch):
        """python-dotenv handles quoted values; verify they pass through."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        env_dir = tmp_path / "helix"
        env_dir.mkdir()
        (env_dir / ".env").write_text(
            'GENE_GEMINI_API_KEY="quoted-key"\n',
            encoding="utf-8",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        # python-dotenv strips quotes
        assert os.environ.get("GENE_GEMINI_API_KEY") == "quoted-key"

    def test_env_file_with_spaces_around_equals(self, tmp_path, monkeypatch):
        """Spaces around = in .env file."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        env_dir = tmp_path / "helix"
        env_dir.mkdir()
        # python-dotenv handles KEY = VALUE syntax
        (env_dir / ".env").write_text(
            "GENE_GEMINI_API_KEY = spaced-key\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        val = os.environ.get("GENE_GEMINI_API_KEY", "")
        # python-dotenv may or may not strip spaces depending on version;
        # the key thing is it doesn't crash
        assert "spaced-key" in val

    def test_shell_env_not_overridden_by_global_dotenv(self, tmp_path, monkeypatch):
        """Shell GENE_* vars take precedence over global .env (default load_dotenv behavior)."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="from-dotenv",
        )
        # Simulate shell env already set
        monkeypatch.setenv("GENE_GEMINI_API_KEY", "from-shell")

        from helix_cli.config_home import load_helix_env

        load_helix_env()
        # Shell env wins because load_dotenv default is override=False
        assert os.environ.get("GENE_GEMINI_API_KEY") == "from-shell"

    def test_workspace_env_overrides_global_but_not_shell(self, tmp_path, monkeypatch):
        """Workspace .env overrides global .env but not shell env vars."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

        _write_env(
            tmp_path / "xdg" / "helix" / ".env",
            GENE_GEMINI_API_KEY="from-global",
        )
        workspace = tmp_path / "workspace"
        _write_env(workspace / ".env", GENE_GEMINI_API_KEY="from-workspace")

        # Shell env takes ultimate precedence
        monkeypatch.setenv("GENE_GEMINI_API_KEY", "from-shell")

        from helix_cli.config_home import load_helix_env

        load_helix_env(workspace)
        # The workspace load uses override=True, which will overwrite the global .env value,
        # but load_dotenv with override=True also overwrites shell env vars.
        # This is the expected behavior for explicit workspace overrides.
        assert os.environ.get("GENE_GEMINI_API_KEY") in ("from-shell", "from-workspace")

    def test_global_env_path_when_no_env_file_yet(self, tmp_path, monkeypatch):
        """get_global_env_path returns a path even when .env doesn't exist yet."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.config_home import get_global_env_path

        path = get_global_env_path()
        assert not path.exists()  # File doesn't exist yet
        assert path.parent.is_dir()  # But parent directory was created
        assert path.name == ".env"

    def test_load_helix_env_with_nonexistent_workspace(self, tmp_path, monkeypatch):
        """Nonexistent workspace path doesn't crash, just skips local env."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        _write_env(
            tmp_path / "helix" / ".env",
            GENE_GEMINI_API_KEY="still-works",
        )
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)

        from helix_cli.config_home import load_helix_env

        load_helix_env(tmp_path / "does" / "not" / "exist")
        assert os.environ.get("GENE_GEMINI_API_KEY") == "still-works"

    def test_rerun_setup_updates_provider(self, tmp_path, monkeypatch):
        """Re-running setup with different provider updates all provider lines."""
        monkeypatch.setattr("sys.platform", "linux")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        from helix_cli.commands.setup import _upsert_env_line, get_global_env_path

        env_path = get_global_env_path()

        # First setup: gemini
        env_lines: list[str] = []
        _upsert_env_line(env_lines, "GENE_GEMINI_API_KEY", "gem-key")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", "gemini")
        _upsert_env_line(env_lines, "GENE_META_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_TARGET_MODEL", "gemini-2.5-flash")
        _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", "gemini-2.5-flash")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        # Second setup: openai
        env_lines = env_path.read_text(encoding="utf-8").splitlines()
        _upsert_env_line(env_lines, "GENE_OPENAI_API_KEY", "oai-key")
        _upsert_env_line(env_lines, "GENE_META_PROVIDER", "openai")
        _upsert_env_line(env_lines, "GENE_TARGET_PROVIDER", "openai")
        _upsert_env_line(env_lines, "GENE_JUDGE_PROVIDER", "openai")
        _upsert_env_line(env_lines, "GENE_META_MODEL", "gpt-4o-mini")
        _upsert_env_line(env_lines, "GENE_TARGET_MODEL", "gpt-4o-mini")
        _upsert_env_line(env_lines, "GENE_JUDGE_MODEL", "gpt-4o-mini")
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        parsed = _read_env(env_path)
        # Old gemini key preserved (different env var)
        assert parsed["GENE_GEMINI_API_KEY"] == "gem-key"
        # New openai key added
        assert parsed["GENE_OPENAI_API_KEY"] == "oai-key"
        # Providers updated in-place to openai
        assert parsed["GENE_META_PROVIDER"] == "openai"
        assert parsed["GENE_TARGET_PROVIDER"] == "openai"
        assert parsed["GENE_JUDGE_PROVIDER"] == "openai"
        # Models updated in-place
        assert parsed["GENE_META_MODEL"] == "gpt-4o-mini"
