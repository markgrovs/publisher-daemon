"""
Publisher Daemon: Shared logic for publishing Hugo sites from Obsidian vaults.
"""

from .core import PublisherDaemon
from .sync import SyncConfig
from .frontmatter import parse_frontmatter, update_publish_state
from .git_ops import (
    run_git,
    fetch_origin,
    checkout_branch,
    get_status,
    add_paths,
    commit,
    push_branch,
    get_commit_hash,
)
from .image_processor import optimize_image, convert_wikilinks, process_markdown_and_assets

__all__ = [
    "PublisherDaemon",
    "SyncConfig",
    "parse_frontmatter",
    "update_publish_state",
    "run_git",
    "fetch_origin",
    "checkout_branch",
    "get_status",
    "add_paths",
    "commit",
    "push_branch",
    "get_commit_hash",
    "optimize_image",
    "convert_wikilinks",
    "process_markdown_and_assets",
]
