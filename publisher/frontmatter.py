"""
Frontmatter parsing and PUBLISH.md state management.
"""

import time
from pathlib import Path
from typing import Dict, Tuple


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """
    Parse YAML frontmatter from a file.
    Returns (dict of key-value pairs, body text).
    """
    if not text.startswith("---"):
        return {}, text
    
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    
    raw_yaml = parts[1]
    body = parts[2]
    data = {}
    
    for line in raw_yaml.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip().strip("'").strip('"')
    
    return data, body


def update_publish_state(publish_file: Path, action: str, status_msg: str) -> None:
    """
    Update PUBLISH.md with action, timestamp, and status.
    """
    if not publish_file.exists():
        return
    
    text = publish_file.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    header = [
        "---",
        f"action: {action}",
        "target: current",
        f"last_run: {timestamp}",
        f"last_status: {status_msg}",
        "---",
        ""
    ]
    
    newline = "\n"
    new_content = newline.join(header) + body.lstrip()
    publish_file.write_text(new_content, encoding="utf-8")
