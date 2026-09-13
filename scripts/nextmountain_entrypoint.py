#!/usr/bin/env python3
"""
Entry point for NextMountain-Blog publisher daemon.

Site-specific configuration and logging setup.
Usage: python3 scripts/nextmountain_entrypoint.py [--poll-interval <seconds>]
"""

import sys
import argparse
import logging
from pathlib import Path

from publisher import PublisherDaemon, SyncConfig


def main():
    parser = argparse.ArgumentParser(description="NextMountain-Blog Publisher")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Polling interval in seconds (default: 5)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Site-specific paths (running in Docker)
    vault_dir = Path("/vault")
    repo_dir = Path("/repo")
    publish_file = vault_dir / "PUBLISH.md"

    # Ownership: vault subdir -> repo subdir
    # NextMountain-Blog uses flat structure: posts/, drafts/, pages/
    ownership = {
        "posts": "content/posts",
        "drafts": "content/drafts",
        "pages": "content",
    }

    config = SyncConfig(
        vault_dir=vault_dir,
        repo_dir=repo_dir,
        ownership=ownership,
        max_image_width=1800,
        image_quality=82,
    )

    daemon = PublisherDaemon(
        config=config,
        publish_file=publish_file,
        preview_branch="preview",
        production_branch="main",
        poll_interval=args.poll_interval,
    )

    try:
        daemon.run()
    except Exception as e:
        logging.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
