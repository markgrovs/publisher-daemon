"""
Vault→Repo synchronization logic for site-specific ownership paths.

Mirror semantics: the vault is the single source of truth for owned content.
Every sync rewrites all owned content into the repo, then prunes any path
the daemon previously wrote that no longer exists in the vault. A manifest
(.publisher-manifest.json in the repo root) records what the daemon wrote,
so legacy files the daemon never touched are never pruned.
"""

import json
import logging
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

from .frontmatter import parse_frontmatter
from .image_processor import process_markdown_and_assets

MANIFEST_NAME = ".publisher-manifest.json"


def find_post_markdown(post_dir: Path) -> Optional[Path]:
    """
    Locate the markdown file for a post bundle.
    Prefers index.md; falls back to the sole .md file in the folder
    (handles names like index.md.md or my-post.md).
    """
    index_file = post_dir / "index.md"
    if index_file.exists():
        return index_file
    md_files = sorted(post_dir.glob("*.md"))
    if len(md_files) == 1:
        return md_files[0]
    return None


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


def _load_manifest(repo_dir: Path) -> dict:
    manifest_file = repo_dir / MANIFEST_NAME
    if manifest_file.exists():
        try:
            return json.loads(manifest_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logging.warning("Manifest unreadable; starting fresh: %s", manifest_file)
    return {"paths": []}


def _save_manifest(repo_dir: Path, paths: List[str]) -> None:
    manifest_file = repo_dir / MANIFEST_NAME
    manifest_file.write_text(
        json.dumps({"paths": sorted(paths)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _prune_missing(config: SyncConfig, previous: List[str], current: set) -> List[Path]:
    """
    Remove repo paths the daemon previously wrote that are no longer
    produced from the vault. Returns list of removed paths.
    """
    removed = []
    for rel in previous:
        if rel in current:
            continue
        target = config.repo_dir / rel
        if not target.exists():
            continue
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        logging.info("Pruned (no longer in vault): %s", rel)
        removed.append(target)
    return removed


def sync_owned(config: SyncConfig, include_drafts: bool = True) -> List[Path]:
    """
    Mirror all owned vault content into the repo.

    Writes every publishable vault item (drafts included, with their
    draft flag intact — Hugo's --buildDrafts flag decides visibility),
    then prunes previously-written paths that vanished from the vault.

    Returns list of repo paths that were written or pruned (candidates
    for git staging). Git status remains the source of truth for
    whether anything actually changed.
    """
    written: List[Path] = []
    current_rels: set = set()

    for vault_subdir, repo_subdir in config.ownership.items():
        vault_path = config.vault_dir / vault_subdir
        if not vault_path.exists():
            logging.info("Vault subdir not found: %s (skipping)", vault_subdir)
            continue

        repo_path = config.repo_dir / repo_subdir
        repo_path.mkdir(parents=True, exist_ok=True)

        if vault_subdir == "posts":
            # Handle post bundles: YYYY-MM-DD-slug/<markdown>
            for post_dir in sorted(vault_path.iterdir()):
                if not post_dir.is_dir():
                    continue
                index_file = find_post_markdown(post_dir)
                if index_file is None:
                    logging.warning("Post bundle %s has no markdown file; skipping", post_dir.name)
                    continue
                if is_draft(index_file) and not include_drafts:
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
                written.append(bundle_dir)
                current_rels.add(str(bundle_dir.relative_to(config.repo_dir)))

        else:
            # Handle flat files: links/, pages/ etc.
            # Copy .md files directly; optional image handling per file.
            for md_file in vault_path.glob("*.md"):
                if is_draft(md_file) and not include_drafts:
                    logging.info("Skipping draft file: %s", md_file.name)
                    continue

                dest = repo_path / md_file.name
                dest.write_text(md_file.read_text(encoding="utf-8"), encoding="utf-8")
                written.append(dest)
                current_rels.add(str(dest.relative_to(config.repo_dir)))
                logging.info("Synced file: %s -> %s", md_file.name, repo_subdir)

    # Mirror: prune daemon-written paths that no longer exist in the vault.
    manifest = _load_manifest(config.repo_dir)
    removed = _prune_missing(config, manifest.get("paths", []), current_rels)
    _save_manifest(config.repo_dir, current_rels)

    return written + removed


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
