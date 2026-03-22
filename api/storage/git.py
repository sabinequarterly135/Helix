"""Git operations for prompt versioning in a separate prompts repo.

All subprocess calls target the prompts directory (cwd=self.prompts_dir),
NOT the project repo. The prompts directory is initialized as its own
git repository.
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from api.exceptions import StorageError

logger = logging.getLogger(__name__)


class GitStorage:
    """Git-based version control for prompt files.

    Operates on a separate git repository in the prompts directory.
    All git commands use cwd=self.prompts_dir to isolate from the project repo.
    """

    def __init__(self, prompts_dir: Path):
        self.prompts_dir = prompts_dir

    async def init_repo(self) -> None:
        """Initialize git repo in prompts directory if not already a repo."""
        if (self.prompts_dir / ".git").exists():
            return

        try:
            await asyncio.to_thread(
                subprocess.run,
                ["git", "init"],
                cwd=self.prompts_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Initialized git repo at %s", self.prompts_dir)
        except subprocess.CalledProcessError as e:
            raise StorageError(f"Failed to initialize git repo: {e.stderr}") from e

    async def commit_prompt(self, prompt_id: str, message: str) -> str:
        """Stage and commit prompt files, return commit hash.

        Args:
            prompt_id: The prompt directory name to stage.
            message: Git commit message.

        Returns:
            The commit hash (full SHA).

        Raises:
            StorageError: If the prompt directory doesn't exist or git fails.
        """
        prompt_dir = self.prompts_dir / prompt_id
        if not prompt_dir.exists():
            raise StorageError(f"Prompt directory does not exist: {prompt_dir}")

        try:
            await self._run_git(["git", "add", str(prompt_id)])
            await self._run_git(["git", "commit", "-m", message])
            result = await self._run_git(["git", "rev-parse", "HEAD"])
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise StorageError(f"Git commit failed for '{prompt_id}': {e.stderr}") from e

    async def get_log(self, prompt_id: str, max_count: int = 20) -> list[dict]:
        """Return commit history for a prompt.

        Args:
            prompt_id: The prompt directory name to get history for.
            max_count: Maximum number of log entries to return.

        Returns:
            List of dicts with keys: hash, message, timestamp.
            Ordered most-recent-first.
        """
        try:
            result = await self._run_git(
                [
                    "git",
                    "log",
                    f"--max-count={max_count}",
                    "--format=%H%n%s%n%aI",
                    "--",
                    str(prompt_id),
                ]
            )
        except subprocess.CalledProcessError as e:
            raise StorageError(f"Git log failed for '{prompt_id}': {e.stderr}") from e

        entries = []
        lines = result.stdout.strip().split("\n")
        # Each entry is 3 lines: hash, subject, ISO timestamp
        for i in range(0, len(lines) - 2, 3):
            entries.append(
                {
                    "hash": lines[i],
                    "message": lines[i + 1],
                    "timestamp": lines[i + 2],
                }
            )
        return entries

    async def get_file_at_commit(self, prompt_id: str, commit_hash: str) -> str:
        """Retrieve prompt.md content at a specific git commit.

        Args:
            prompt_id: The prompt directory name.
            commit_hash: Full or short git commit hash.

        Returns:
            The file content at that commit.

        Raises:
            StorageError: If the commit hash is invalid or file doesn't exist at that commit.
        """
        try:
            result = await self._run_git(["git", "show", f"{commit_hash}:{prompt_id}/prompt.md"])
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise StorageError(
                f"Cannot retrieve '{prompt_id}/prompt.md' at commit {commit_hash}: {e.stderr}"
            ) from e

    async def _run_git(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a git command in the prompts directory."""
        return await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=self.prompts_dir,
            check=True,
            capture_output=True,
            text=True,
        )
