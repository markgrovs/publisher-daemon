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


def _yaml_quote(value: str) -> str:
    """
    Quote a value for YAML frontmatter so Obsidian's strict property
    parser accepts it. Unquoted values containing ": " (like
    "Preview published: abc123") or bare timestamps render as invalid
    properties in Obsidian. Newlines are collapsed so multi-line
    error messages stay within a single property line.
    """
    collapsed = " ".join(value.split())
    escaped = collapsed.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
        f"last_run: {_yaml_quote(timestamp)}",
        f"last_status: {_yaml_quote(status_msg)}",
        "---",
        ""
    ]
    
    newline = "\n"
    new_content = newline.join(header) + body.lstrip()
    publish_file.write_text(new_content, encoding="utf-8")
