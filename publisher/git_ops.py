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
    """Commit staged changes with an explicit author identity.

    Bind-mounted repos may lack user.name/user.email config, and the
    container runs as root so git cannot auto-detect an email. Identity
    comes from PUBLISHER_GIT_NAME / PUBLISHER_GIT_EMAIL env vars.
    """
    import os
    name = os.environ.get("PUBLISHER_GIT_NAME", "Publisher Daemon")
    email = os.environ.get("PUBLISHER_GIT_EMAIL", "publisher@localhost")
    run_git(repo_dir, [
        "-c", f"user.name={name}",
        "-c", f"user.email={email}",
        "commit", "-m", message,
    ])


def merge_branch(repo_dir: Path, source_branch: str) -> str:
    """
    Merge source_branch into the currently checked-out branch.
    Uses --no-ff so the merge is always recorded as a merge commit,
    making production history explicit. Returns git's summary output.

    A merge creates a commit, so it needs the same explicit identity
    injection as commit() (bind-mounted repos lack user.name/user.email).
    """
    import os
    name = os.environ.get("PUBLISHER_GIT_NAME", "Publisher Daemon")
    email = os.environ.get("PUBLISHER_GIT_EMAIL", "publisher@localhost")
    result = run_git(repo_dir, [
        "-c", f"user.name={name}",
        "-c", f"user.email={email}",
        "merge", "--no-ff", "-m", f"Merge {source_branch} into production", source_branch,
    ])
    return result.stdout.strip()


def push_branch(repo_dir: Path, branch: str) -> None:
    """Push branch to origin."""
    run_git(repo_dir, ["push", "origin", branch])


def get_commit_hash(repo_dir: Path) -> str:
    """Get short commit hash; returns stdout stripped."""
    result = run_git(repo_dir, ["rev-parse", "--short", "HEAD"])
    return result.stdout.strip()
