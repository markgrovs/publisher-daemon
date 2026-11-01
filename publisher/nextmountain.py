"""Field Notebook adapter. Enabled only by the Next Mountain entrypoint.

Validate and render into staging before changing repository content. Copy only
explicitly referenced delivery assets; preserve real YAML lists and scalars.
"""
import hashlib
import math
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from PIL import Image, ImageOps

from .sync import SyncConfig, MANIFEST_NAME, _load_manifest, _save_manifest

OWNERSHIP = {"posts": "content/posts", "cairns": "content/cairns",
             "journeys": "content/journeys", "home": "content/home",
             "pages": "content", "drafts": "content/drafts"}
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
DELIVERY_TYPES = IMAGE_TYPES | {".mp4", ".pdf", ".txt", ".gpx", ".csv", ".json"}
LINK = re.compile(r'(!?\[[^\]\n]*\]\()(<[^>\n]+>|[^\s)]+)(\s+"[^"\n]*")?(\))')
WIKI_IMAGE = re.compile(r'!\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')
VIDEO = re.compile(r'({{<\s*ambient-video\b)(.*?)(>}})', re.S)


def create_config(vault_dir, repo_dir):
    return SyncConfig(vault_dir=Path(vault_dir), repo_dir=Path(repo_dir),
                      ownership=dict(OWNERSHIP), sync_handler=sync_nextmountain)


def metadata(text):
    match = re.match(r'\A---\s*\n(.*?)\n---(?:\s*\n|$)', text, re.S)
    if not match:
        raise ValueError("Expected YAML frontmatter bounded by --- lines")
    data = yaml.safe_load(match.group(1)) or {}
    if not isinstance(data, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    return data, text[match.end():]


def validate(data):
    journeys = data.get("journeys", [])
    if not isinstance(journeys, list) or any(not isinstance(j, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', j) for j in journeys):
        raise ValueError("journeys must be a YAML list of stable lowercase identifiers")
    if data.get("location") is not None and not isinstance(data["location"], str):
        raise ValueError("location must be a display-name string")
    coords = [data.get("lat"), data.get("long")]
    supplied = [v is not None and v != "" for v in coords]
    if any(supplied) and not all(supplied):
        raise ValueError("Supply both lat and long")
    if all(supplied):
        for value, maximum in zip(coords, (90, 180)):
            if isinstance(value, bool):
                raise ValueError("Coordinates must be numeric")
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError("Coordinates must be numeric") from None
            if not math.isfinite(number) or abs(number) > maximum:
                raise ValueError("Coordinates out of range")
    if "draft" in data and not isinstance(data["draft"], bool):
        raise ValueError("draft must be a YAML boolean")


def safe_file(path, root):
    path = Path(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes permitted source: {path.name}")
    if not path.is_file():
        raise ValueError(f"Referenced file missing: {path.name}")
    return path


def render_bundle(source, target, vault, index_name, config, home=False):
    data, body = metadata(source.read_text(encoding="utf-8"))
    validate(data)
    if home:
        data["headless"] = True
    target.mkdir(parents=True, exist_ok=True)
    copied = {}

    def asset(reference, image_only=False):
        reference = unquote(str(reference).strip('<>'))
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or Path(reference).is_absolute() or '..' in Path(reference).parts:
            raise ValueError(f"Use a local delivery asset path: {reference}")
        candidates = [(source.parent/reference, source.parent), (vault/'attachments'/reference, vault/'attachments')]
        found = None
        for path, root in candidates:
            if path.exists():
                found = safe_file(path, root)
                safe_file(found, vault)
                break
        if found is None:
            raise ValueError(f"Referenced asset missing: {reference}")
        suffix = found.suffix.lower()
        if suffix not in (IMAGE_TYPES if image_only else DELIVERY_TYPES):
            raise ValueError(f"Unsupported delivery asset: {reference}")
        if found.stat().st_size > 50 * 1024 * 1024:
            raise ValueError(f"Delivery asset exceeds 50 MiB: {reference}")
        key = str(found.resolve())
        if key in copied:
            return copied[key]
        digest = hashlib.sha256(str(found.relative_to(vault)).encode()).hexdigest()[:12]
        stem = re.sub(r'[^A-Za-z0-9_-]', '-', found.stem)
        relative = f'media/{digest}-{stem}{suffix}'
        dest = target/relative
        dest.parent.mkdir(exist_ok=True)
        if suffix in IMAGE_TYPES:
            with Image.open(found) as original:
                image = ImageOps.exif_transpose(original)
                if image.width > config.max_image_width:
                    image = image.resize((config.max_image_width, max(1, round(image.height * config.max_image_width / image.width))), Image.Resampling.LANCZOS)
                # Preserve PNG transparency; re-encode without original metadata.
                if suffix in {'.jpg', '.jpeg'}:
                    image = image.convert('RGB')
                    image.save(dest, 'JPEG', quality=config.image_quality, optimize=True)
                elif suffix == '.png':
                    image.save(dest, 'PNG', optimize=True)
                else:
                    image.save(dest, 'WEBP', quality=config.image_quality)
        else:
            shutil.copyfile(found, dest)
        copied[key] = relative
        return relative

    def wiki(match):
        path, alt = match.groups()
        alt = alt or Path(path).stem
        return f'![{alt}]({asset(path, image_only=True)})'

    body = WIKI_IMAGE.sub(wiki, body)

    def link(match):
        prefix, url, caption, end = match.groups()
        # Wikilink output is already in its destination form.
        if url in copied.values():
            return match.group(0)
        remote = urlsplit(url.strip('<>'))
        if remote.scheme or remote.netloc or url.startswith(('/', '#')):
            if prefix.startswith('!'):
                raise ValueError("Theme images must be local page resources")
            return match.group(0)
        return prefix + asset(url, image_only=prefix.startswith('!')) + (caption or '') + end

    body = LINK.sub(link, body)
    def video(match):
        attrs = re.sub(r'\b(src|poster)="([^"]+)"', lambda m: f'{m[1]}="{asset(m[2], image_only=m[1] == "poster")}"', match[2])
        return match[1] + attrs + match[3]
    body = VIDEO.sub(video, body)
    if data.get('thumbnail'):
        data['thumbnail'] = asset(data['thumbnail'], image_only=True)
    if data.get('home_photos'):
        if not isinstance(data['home_photos'], list) or len(data['home_photos']) > 2:
            raise ValueError("home_photos must be a list of at most two photos")
        for photo in data['home_photos']:
            if not isinstance(photo, dict) or not isinstance(photo.get('alt'), str) or not photo['alt'].strip():
                raise ValueError("Each homepage photo requires author-written alt text")
            photo['src'] = asset(photo['src'], image_only=True)
    (target/index_name).write_text('---\n' + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + '---\n\n' + body.lstrip(), encoding='utf-8')


def bundles(folder, index_name):
    if not folder.exists():
        return
    seen = set()
    for item in sorted(folder.iterdir()):
        if item.name.startswith('.'):
            continue
        source = None
        if item.is_dir():
            source = item/index_name
            if not source.exists():
                folder_note = item / f"{item.name}.md"
                choices = list(item.glob('*.md'))
                if folder_note.is_file():
                    source = folder_note
                elif len(choices) == 1:
                    source = choices[0]
                elif not choices:
                    # Attachment-only directories are not content bundles.
                    # Do not silently ignore notes nested in organizational folders.
                    if any(item.rglob('*.md')):
                        raise ValueError(f"Nested notes in {item.name}: put each content bundle directly in {folder}")
                    continue
                else:
                    raise ValueError(f"Bundle {item.name} needs {index_name}, {item.name}.md, or one Markdown file")
            slug = item.name
        elif item.suffix == '.md':
            if item.name == '_index.md':
                continue
            source, slug = item, item.stem
        else:
            continue
        if slug in seen or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', slug):
            raise ValueError(f"Duplicate or invalid bundle identifier: {slug}")
        seen.add(slug)
        yield slug, safe_file(source, folder)


def sync_nextmountain(config, include_drafts=True):
    vault, repo = config.vault_dir, config.repo_dir
    if not vault.is_dir():
        raise ValueError("Vault directory missing; refusing to prune")
    repo.mkdir(parents=True, exist_ok=True)
    previous = _load_manifest(repo).get('paths', [])
    prior_files = set()
    for rel in previous:
        p = Path(rel)
        valid = (p.parts and p.parts[0] == 'content' and
                 (len(p.parts) == 2 and p.suffix == '.md' or
                  len(p.parts) >= 3 and p.parts[1] in {'posts','cairns','journeys','home','drafts'}))
        if not valid or '..' in p.parts or not (repo/p).resolve().is_relative_to(repo):
            raise ValueError(f"Unsafe manifest path: {rel}")
        target = repo/p
        if target.is_dir():
            prior_files.update(str(f.relative_to(repo)) for f in target.rglob('*') if f.is_file())
        else:
            prior_files.add(rel)
    with tempfile.TemporaryDirectory(prefix='nextmountain-stage-') as tmp:
        stage = Path(tmp)
        for section, index in [('posts','index.md'),('cairns','index.md'),('journeys','_index.md')]:
            for slug, source in bundles(vault/section, index):
                data, _ = metadata(source.read_text())
                if data.get('draft') is True and not include_drafts:
                    continue
                render_bundle(source, stage/'content'/section/slug, vault, index, config)
        if (vault/'home/index.md').exists():
            source = safe_file(vault/'home/index.md', vault)
            data, _ = metadata(source.read_text())
            if include_drafts or data.get('draft') is not True:
                render_bundle(source, stage/'content/home', vault, 'index.md', config, home=True)
        for section, dest in [('pages','content'),('drafts','content/drafts')]:
            for source in sorted((vault/section).glob('*.md')):
                safe_file(source, vault)
                data, _ = metadata(source.read_text())
                validate(data)
                if data.get('draft') is True and not include_drafts:
                    continue
                target = stage/dest/source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(), encoding='utf-8')
        files = {str(p.relative_to(stage)): p for p in stage.rglob('*') if p.is_file()}
        # Check every destination before writing or pruning (including legacy manifests).
        for rel in set(files) | prior_files:
            if not (repo/rel).resolve().is_relative_to(repo):
                raise ValueError(f"Destination escapes repository: {rel}")
        touched = []
        for rel, source in files.items():
            dest = repo/rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            touched.append(dest)
        for rel in sorted(prior_files - files.keys()):
            target = repo/rel
            if target.is_file():
                target.unlink()
                touched.append(target)
        _save_manifest(repo, list(files))
        return touched
