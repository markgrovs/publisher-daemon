"""
Vault→Repo synchronization logic for site-specific ownership paths.
"""

import logging
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

from .frontmatter import parse_frontmatter
from .image_processor import process_markdown_and_assets


@dataclass
class SyncConfig:
    """
    Maps vault folder → repo folder ownership.
    Each site defines its own config to maintain separation of concerns.
    """
    vault_dir: Path
    repo_dir: Path

    # Ownership mappings: vault_path -> repo_path
    # Example: posts -> content/posts, pages -> content/
    ownership: dict  # {vault_subdir: repo_subdir}

    max_image_width: int = 1800
    image_quality: int = 82

    def __post_init__(self):
        self.vault_dir = Path(self.vault_dir).resolve()
        self.repo_dir = Path(self.repo_dir).resolve()


def is_draft(md_file: Path) -> bool:
    """Check if a file has draft: true in frontmatter."""
    text = md_file.read_text(encoding="utf-8")
    fm, _ = parse_frontmatter(text)
    return fm.get("draft", "").lower() in ("true", "yes")


def sync_owned(config: SyncConfig) -> List[Path]:
    """
    Scan vault for publishable posts under owned paths.
    Create page bundles in the repo.
    Returns list of modified/created bundle directories.
    """
    published = []

    for vault_subdir, repo_subdir in config.ownership.items():
        vault_path = config.vault_dir / vault_subdir
        if not vault_path.exists():
            logging.info("Vault subdir not found: %s (skipped)", vault_subdir)
            continue

        repo_path = config.repo_dir / repo_subdir
        repo_path.mkdir(parents=True, exist_ok=True)

        if vault_subdir == "posts":
            # Handle post bundles: YYYY-MM-DD-slug/index.md
            for post_dir in sorted(vault_path.iterdir()):
                if not post_dir.is_dir():
                    continue
                index_file = post_dir / "index.md"
                if not index_file.exists():
                    continue
                if is_draft(index_file):
                    logging.info("Skipping draft post: %s", post_dir.name)
                    continue

                # Create page bundle in repo
                bundle_dir = repo_path / post_dir.name
                process_markdown_and_assets(
                    index_file,
                    bundle_dir,
                    config.vault_dir,
                    max_width=config.max_image_width,
                    quality=config.image_quality,
                )
                published.append(bundle_dir)

        else:
            # Handle flat files: links/, pages/ etc.
            # Copy .md files directly; optional image handling per file.
            for md_file in vault_path.glob("*.md"):
                if is_draft(md_file):
                    logging.info("Skipping draft file: %s", md_file.name)
                    continue

                dest = repo_path / md_file.name
                dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")
                published.append(dest)
                logging.info("Synced file: %s -> %s", md_file.name, repo_subdir)

    return published


def clean_legacy(config: SyncConfig, keep_paths: Optional[List[str]] = None) -> None:
    """
    (Optional) Remove legacy repo files not tracked by the vault.
    Use with caution; typically skipped to preserve legacy posts.
    """
    if keep_paths is None:
        keep_paths = []
    for vault_subdir, repo_subdir in config.ownership.items():
        repo_path = config.repo_dir / repo_subdir
        if not repo_path.exists():
            continue
        for item in repo_path.iterdir():
            if str(item) in keep_paths or item.name.startswith("."):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
