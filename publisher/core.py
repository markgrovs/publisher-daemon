"""
Core publisher orchestration: watch vault, process, commit, push.
"""

import logging
import time
from pathlib import Path
from typing import Optional

from .frontmatter import update_publish_state
from .git_ops import (
    fetch_origin,
    checkout_branch,
    get_status,
    add_paths,
    commit,
    push_branch,
    get_commit_hash,
)
from .sync import sync_owned, SyncConfig


class PublisherDaemon:
    """
    Main orchestration loop: watch PUBLISH.md, sync vault, commit, push.
    Each site creates its own daemon instance with its SyncConfig.
    """

    def __init__(
        self,
        config: SyncConfig,
        publish_file: Path,
        preview_branch: str = "preview",
        production_branch: str = "main",
        poll_interval: int = 5,
    ):
        self.config = config
        self.publish_file = Path(publish_file)
        self.preview_branch = preview_branch
        self.production_branch = production_branch
        self.poll_interval = poll_interval

        self.logger = logging.getLogger(self.__class__.__name__)

    def read_action(self) -> Optional[str]:
        """Read the current action from PUBLISH.md."""
        if not self.publish_file.exists():
            return None
        text = self.publish_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("action:"):
                action = line.split(":", 1)[1].strip()
                return action if action != "idle" else None
        return None

    def handle_action(self, action: str) -> None:
        """Process the requested action."""
        try:
            if action == "build-preview":
                self._do_build_preview()
            elif action == "publish-production":
                self._do_publish_production()
            else:
                self.logger.warning("Unknown action: %s", action)
        except Exception as e:
            self.logger.error("Action failed: %s", e, exc_info=True)
            update_publish_state(self.publish_file, "idle", f"Error: {e}")

    def _do_build_preview(self) -> None:
        """Sync vault, commit, and push to preview branch."""
        self.logger.info("=== BUILD-PREVIEW started ===")
        
        try:
            self.logger.info("→ Fetching origin...")
            fetch_origin(self.config.repo_dir)
            self.logger.info("✓ Fetch complete")
            
            self.logger.info("→ Checking out preview branch...")
            checkout_branch(self.config.repo_dir, self.preview_branch)
            self.logger.info("✓ Checkout complete")

            self.logger.info("→ Syncing vault to repo (drafts included for preview)...")
            published = sync_owned(self.config, include_drafts=True)
            if not published:
                self.logger.info("✗ No changes synced from vault.")
                update_publish_state(self.publish_file, "idle", "No changes")
                return
            self.logger.info("✓ Synced %d item(s): %s", len(published), [str(p.relative_to(self.config.repo_dir)) for p in published])

            self.logger.info("→ Checking git status...")
            status = get_status(self.config.repo_dir)
            if not status:
                self.logger.info("✗ No staged changes after sync.")
                update_publish_state(self.publish_file, "idle", "No changes")
                return
            self.logger.info("✓ Git status:\n%s", status)

            self.logger.info("→ Staging files...")
            add_paths(self.config.repo_dir, *[str(p) for p in published])
            self.logger.info("✓ Files staged")
            
            self.logger.info("→ Committing...")
            commit(self.config.repo_dir, "Automated MarkGroves-US publish (preview)")
            self.logger.info("✓ Commit created")
            
            self.logger.info("→ Pushing to preview branch...")
            push_branch(self.config.repo_dir, self.preview_branch)
            self.logger.info("✓ Push complete")

            commit_hash = get_commit_hash(self.config.repo_dir)
            msg = f"Preview published: {commit_hash}"
            self.logger.info("=== BUILD-PREVIEW SUCCESS: %s ===", msg)
            update_publish_state(self.publish_file, "idle", msg)
        except Exception as e:
            self.logger.error("=== BUILD-PREVIEW FAILED: %s ===", e, exc_info=True)
            raise

    def _do_publish_production(self) -> None:
        """Merge preview into production and push."""
        self.logger.info("=== PUBLISH-PRODUCTION started ===")
        
        try:
            self.logger.info("→ Fetching origin...")
            fetch_origin(self.config.repo_dir)
            self.logger.info("✓ Fetch complete")
            
            self.logger.info("→ Checking out preview branch...")
            checkout_branch(self.config.repo_dir, self.preview_branch)
            self.logger.info("✓ Checkout complete")

            self.logger.info("→ Syncing vault to repo (drafts excluded for production)...")
            published = sync_owned(self.config, include_drafts=False)
            if not published:
                self.logger.info("✗ No changes synced from vault.")
                update_publish_state(self.publish_file, "idle", "No changes")
                return
            self.logger.info("✓ Synced %d item(s): %s", len(published), [str(p.relative_to(self.config.repo_dir)) for p in published])

            self.logger.info("→ Checking git status...")
            status = get_status(self.config.repo_dir)
            if not status:
                self.logger.info("✗ No staged changes after sync.")
                update_publish_state(self.publish_file, "idle", "No changes")
                return
            self.logger.info("✓ Git status:\n%s", status)

            self.logger.info("→ Staging files...")
            add_paths(self.config.repo_dir, *[str(p) for p in published])
            self.logger.info("✓ Files staged")
            
            self.logger.info("→ Committing to preview...")
            commit(self.config.repo_dir, "Automated MarkGroves-US publish (production)")
            self.logger.info("✓ Commit created")
            
            self.logger.info("→ Pushing preview branch...")
            push_branch(self.config.repo_dir, self.preview_branch)
            self.logger.info("✓ Push complete")

            self.logger.info("→ Checking out production branch...")
            checkout_branch(self.config.repo_dir, self.production_branch)
            self.logger.info("✓ Checkout complete")
            
            commit_hash = get_commit_hash(self.config.repo_dir)
            msg = f"Production published: {commit_hash}"
            self.logger.info("=== PUBLISH-PRODUCTION SUCCESS: %s ===", msg)
            update_publish_state(self.publish_file, "idle", msg)
        except Exception as e:
            self.logger.error("=== PUBLISH-PRODUCTION FAILED: %s ===", e, exc_info=True)
            raise

    def run(self) -> None:
        """Main polling loop."""
        self.logger.info("Publisher daemon started. Polling every %d seconds.", self.poll_interval)
        poll_count = 0
        while True:
            poll_count += 1
            try:
                action = self.read_action()
                if action:
                    self.logger.info("[Poll #%d] Action detected: %s", poll_count, action)
                    self.handle_action(action)
                else:
                    self.logger.info("[Poll #%d] No action pending.", poll_count)
            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                break
            except Exception as e:
                self.logger.error("[Poll #%d] Polling error: %s", poll_count, e, exc_info=True)
            
            time.sleep(self.poll_interval)
