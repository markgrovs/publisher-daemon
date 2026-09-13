"""
Image optimization and Markdown wikilink-to-standard-link conversion.
"""

import re
import shutil
import logging
from pathlib import Path
from typing import Set

from PIL import Image

WIKILINK_IMG_PATTERN = re.compile(r"!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
STANDARD_IMG_PATTERN = re.compile(r"!\[(.*?)\]\((.*?)\)")


def optimize_image(
    src_path: Path,
    dest_path: Path,
    max_width: int = 1800,
    quality: int = 82,
) -> None:
    """
    Resize and re-encode an image as JPEG. Falls back to plain copy on failure.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src_path) as img:
            img = img.convert("RGB")
            if img.width > max_width:
                height = int((max_width / img.width) * img.height)
                img = img.resize((max_width, height), Image.Resampling.LANCZOS)
            img.save(dest_path, "JPEG", quality=quality, optimize=True)
            logging.info("Optimized image: %s -> %s", src_path.name, dest_path.name)
    except Exception as e:
        logging.warning("Failed to optimize image %s: %s", src_path.name, e)
        shutil.copy2(src_path, dest_path)


def find_referenced_images(content: str) -> Set[str]:
    """
    Extract image filenames referenced via wikilinks or standard Markdown links.
    """
    referenced = set()
    for match in WIKILINK_IMG_PATTERN.finditer(content):
        referenced.add(match.group(1).strip())
    for match in STANDARD_IMG_PATTERN.finditer(content):
        img_url = match.group(2).strip()
        if not img_url.startswith("http") and not img_url.startswith("/"):
            referenced.add(Path(img_url).name)
    return referenced


def convert_wikilinks(content: str) -> str:
    """
    Convert Obsidian wikilink image syntax to standard Markdown pointing at
    a local images/ subfolder.
    """
    def wikilink_sub(match):
        img_name = Path(match.group(1).strip()).name
        alt = match.group(2).strip() if match.group(2) else img_name
        return f"![{alt}](images/{img_name})"
    return WIKILINK_IMG_PATTERN.sub(wikilink_sub, content)


def process_markdown_and_assets(
    post_md_file: Path,
    target_bundle_dir: Path,
    vault_dir: Path,
    max_width: int = 1800,
    quality: int = 82,
) -> None:
    """
    Copy a post's Markdown file into a Hugo page bundle, optimizing and
    relocating any referenced images, and rewriting wikilinks to standard
    Markdown image syntax pointing at the bundle's images/ subfolder.
    """
    target_bundle_dir.mkdir(parents=True, exist_ok=True)
    images_dest_dir = target_bundle_dir / "images"
    images_dest_dir.mkdir(parents=True, exist_ok=True)

    content = post_md_file.read_text(encoding="utf-8")
    referenced_images = find_referenced_images(content)

    vault_posts_img_dir = post_md_file.parent / "images"
    vault_attachments_dir = vault_dir / "attachments"

    for img_name in referenced_images:
        found_src = None
        if (vault_posts_img_dir / img_name).exists():
            found_src = vault_posts_img_dir / img_name
        elif (vault_attachments_dir / img_name).exists():
            found_src = vault_attachments_dir / img_name
        elif (post_md_file.parent / img_name).exists():
            found_src = post_md_file.parent / img_name

        if found_src:
            dest_file = images_dest_dir / img_name
            optimize_image(found_src, dest_file, max_width=max_width, quality=quality)
        else:
            logging.warning("Referenced image not found: %s", img_name)

    converted_content = convert_wikilinks(content)
    dest_index = target_bundle_dir / "index.md"
    dest_index.write_text(converted_content, encoding="utf-8")
    logging.info("Processed post saved to %s", dest_index)
