"""Tests for GitStorage -- real git operations in temporary directories.

VER-01: Each evolution run that produces an improved prompt creates a git commit.
"""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary directory with an initialized git repo."""
    import subprocess

    repo_dir = tmp_path / "prompts"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return repo_dir


@pytest.fixture
def git_storage(tmp_git_repo: Path):
    """Create a GitStorage instance pointing at the tmp git repo."""
    from api.storage.git import GitStorage

    return GitStorage(tmp_git_repo)


class TestGitStorageInitRepo:
    """Test GitStorage.init_repo creates a git repository."""

    async def test_init_repo_creates_git_directory(self, tmp_path: Path):
        """VER-01: GitStorage.init_repo creates a git repository in the prompts directory."""
        from api.storage.git import GitStorage

        prompts_dir = tmp_path / "new_prompts"
        prompts_dir.mkdir()
        storage = GitStorage(prompts_dir)
        await storage.init_repo()
        assert (prompts_dir / ".git").exists()

    async def test_init_repo_idempotent(self, tmp_git_repo: Path):
        """init_repo does nothing if .git already exists."""
        from api.storage.git import GitStorage

        storage = GitStorage(tmp_git_repo)
        await storage.init_repo()  # Should not raise
        assert (tmp_git_repo / ".git").exists()


class TestGitStorageCommitPrompt:
    """Test GitStorage.commit_prompt stages and commits files."""

    async def test_commit_prompt_returns_hash(self, git_storage, tmp_git_repo: Path):
        """VER-01: GitStorage.commit_prompt returns commit hash."""
        # Create a prompt directory with a file
        prompt_dir = tmp_git_repo / "test-prompt"
        prompt_dir.mkdir()
        (prompt_dir / "prompt.md").write_text("Hello {{ name }}")

        commit_hash = await git_storage.commit_prompt("test-prompt", "Initial prompt")
        assert isinstance(commit_hash, str)
        assert len(commit_hash) >= 7  # Short hash is at least 7 chars

    async def test_commit_prompt_creates_git_commit(self, git_storage, tmp_git_repo: Path):
        """VER-01: Commit appears in git log."""
        import subprocess

        prompt_dir = tmp_git_repo / "my-prompt"
        prompt_dir.mkdir()
        (prompt_dir / "prompt.md").write_text("Test content")

        await git_storage.commit_prompt("my-prompt", "Test commit message")

        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_git_repo,
            capture_output=True,
            text=True,
        )
        assert "Test commit message" in result.stdout

    async def test_commit_nonexistent_prompt_raises_error(self, git_storage):
        """Committing a non-existent prompt directory raises StorageError."""
        from api.exceptions import StorageError

        with pytest.raises(StorageError):
            await git_storage.commit_prompt("nonexistent-prompt", "Should fail")


class TestGitStorageGetLog:
    """Test GitStorage.get_log returns commit history."""

    async def test_get_log_returns_history(self, git_storage, tmp_git_repo: Path):
        """VER-01: GitStorage.get_log returns commit history for a prompt."""
        prompt_dir = tmp_git_repo / "log-prompt"
        prompt_dir.mkdir()

        # Make multiple commits
        (prompt_dir / "prompt.md").write_text("Version 1")
        await git_storage.commit_prompt("log-prompt", "First version")

        (prompt_dir / "prompt.md").write_text("Version 2")
        await git_storage.commit_prompt("log-prompt", "Second version")

        log = await git_storage.get_log("log-prompt")
        assert len(log) == 2
        assert log[0]["message"] == "Second version"  # Most recent first
        assert log[1]["message"] == "First version"

    async def test_get_log_entries_have_required_fields(self, git_storage, tmp_git_repo: Path):
        """Log entries have hash, message, timestamp."""
        prompt_dir = tmp_git_repo / "fields-prompt"
        prompt_dir.mkdir()
        (prompt_dir / "prompt.md").write_text("Content")
        await git_storage.commit_prompt("fields-prompt", "Check fields")

        log = await git_storage.get_log("fields-prompt")
        assert len(log) == 1
        entry = log[0]
        assert "hash" in entry
        assert "message" in entry
        assert "timestamp" in entry

    async def test_get_log_respects_max_count(self, git_storage, tmp_git_repo: Path):
        """get_log limits results with max_count parameter."""
        prompt_dir = tmp_git_repo / "max-prompt"
        prompt_dir.mkdir()

        for i in range(5):
            (prompt_dir / "prompt.md").write_text(f"Version {i}")
            await git_storage.commit_prompt("max-prompt", f"Commit {i}")

        log = await git_storage.get_log("max-prompt", max_count=2)
        assert len(log) == 2
