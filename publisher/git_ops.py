"""
Git operations wrapper for publisher daemon.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def run_git(repo_dir: Path, args: list, check: bool = True) -> subprocess.CompletedProcess:
    """
    Execute a git command in the specified repository.
    Raises RuntimeError if check=True and the command fails.
    """
    import os
    
    # -c safe.directory bypasses git's ownership check for bind-mounted repos
    cmd = ["git", "-c", f"safe.directory={repo_dir}", "-C", str(repo_dir)] + args
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = "ssh -i /root/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
    
    logger.debug("Executing: %s", ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    if result.returncode != 0:
        logger.debug("Git stderr: %s", result.stderr)
        if check:
            raise RuntimeError(f"Git failed: {' '.join(cmd)}\nStderr: {result.stderr}")
    else:
        if result.stdout.strip():
            logger.debug("Git stdout: %s", result.stdout.strip())
    
    return result


def fetch_origin(repo_dir: Path) -> None:
    """Fetch from origin."""
    run_git(repo_dir, ["fetch", "origin", "--prune"])


def checkout_branch(repo_dir: Path, branch: str) -> None:
    """Checkout and reset to origin/branch."""
    run_git(repo_dir, ["checkout", "-B", branch, f"origin/{branch}"])


def get_status(repo_dir: Path) -> str:
    """Get porcelain status; returns stdout."""
    result = run_git(repo_dir, ["status", "--porcelain"], check=False)
    return result.stdout.strip()


def add_paths(repo_dir: Path, *paths: str) -> None:
    """Stage multiple paths."""
    if not paths:
        return
    run_git(repo_dir, ["add"] + list(paths))


def commit(repo_dir: Path, message: str) -> None:
    """Commit staged changes."""
    run_git(repo_dir, ["commit", "-m", message])


def push_branch(repo_dir: Path, branch: str) -> None:
    """Push branch to origin."""
    run_git(repo_dir, ["push", "origin", branch])


def get_commit_hash(repo_dir: Path) -> str:
    """Get short commit hash; returns stdout stripped."""
    result = run_git(repo_dir, ["rev-parse", "--short", "HEAD"])
    return result.stdout.strip()
