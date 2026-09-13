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
        self.logger.info("Starting build-preview...")
        
        fetch_origin(self.config.repo_dir)
        checkout_branch(self.config.repo_dir, self.preview_branch)

        published = sync_owned(self.config)
        if not published:
            self.logger.info("No changes to publish.")
            update_publish_state(self.publish_file, "idle", "No changes")
            return

        status = get_status(self.config.repo_dir)
        if not status:
            self.logger.info("No staged changes after sync.")
            update_publish_state(self.publish_file, "idle", "No changes")
            return

        add_paths(self.config.repo_dir, *[str(p) for p in published])
        commit(self.config.repo_dir, "Publish preview: updated posts and assets")
        push_branch(self.config.repo_dir, self.preview_branch)

        commit_hash = get_commit_hash(self.config.repo_dir)
        msg = f"Preview published: {commit_hash}"
        self.logger.info(msg)
        update_publish_state(self.publish_file, "idle", msg)

    def _do_publish_production(self) -> None:
        """Merge preview into production and push."""
        self.logger.info("Starting publish-production...")
        
        fetch_origin(self.config.repo_dir)
        checkout_branch(self.config.repo_dir, self.preview_branch)

        published = sync_owned(self.config)
        if not published:
            self.logger.info("No changes to publish.")
            update_publish_state(self.publish_file, "idle", "No changes")
            return

        status = get_status(self.config.repo_dir)
        if not status:
            self.logger.info("No staged changes after sync.")
            update_publish_state(self.publish_file, "idle", "No changes")
            return

        add_paths(self.config.repo_dir, *[str(p) for p in published])
        commit(self.config.repo_dir, "Publish production: updated posts and assets")
        push_branch(self.config.repo_dir, self.preview_branch)

        checkout_branch(self.config.repo_dir, self.production_branch)
        commit_hash = get_commit_hash(self.config.repo_dir)
        msg = f"Production published: {commit_hash}"
        self.logger.info(msg)
        update_publish_state(self.publish_file, "idle", msg)

    def run(self) -> None:
        """Main polling loop."""
        self.logger.info("Publisher daemon started. Polling every %d seconds.", self.poll_interval)
        while True:
            try:
                action = self.read_action()
                if action:
                    self.logger.info("Read action: %s", action)
                    self.handle_action(action)
                else:
                    self.logger.debug("No action pending.")
            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                break
            except Exception as e:
                self.logger.error("Polling error: %s", e, exc_info=True)
            
            time.sleep(self.poll_interval)
