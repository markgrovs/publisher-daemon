# Publisher Daemon

Shared publishing logic for Hugo sites (Next Mountain Overland & MarkGroves.us) running on Workbench.

## Architecture

### Modules

- **`publisher/frontmatter.py`** — YAML frontmatter parsing and PUBLISH.md state management
- **`publisher/git_ops.py`** — Git command wrappers (fetch, checkout, commit, push)
- **`publisher/image_processor.py`** — Image optimization and wikilink→Markdown conversion
- **`publisher/sync.py`** — Vault→Repo synchronization with configurable ownership paths
- **`publisher/core.py`** — PublisherDaemon orchestration (polling, action handling, publishing)
- **`publisher/__init__.py`** — Public API exports

### Entrypoints

- **`scripts/nextmountain_entrypoint.py`** — NextMountain-Blog configuration
- **`scripts/markgroves_entrypoint.py`** — MarkGroves.us configuration

Each entrypoint initializes a `SyncConfig` with its site-specific:
- Vault directory and ownership mappings (posts/, pages/, links/, etc. → content/*)
- Publish file location
- Image processing settings (max width, quality)

## Workflow

1. **Vault Sync** — Obsidian Sync pushes changes to `/vault` on Workbench
2. **Polling** — Daemon reads `PUBLISH.md` every 5 seconds
3. **Action** — When action is set, daemon:
   - **build-preview**: Sync vault, commit, push to `preview` branch (triggers Netlify branch deploy)
   - **publish-production**: Merge preview into `main` (triggers Netlify production build)
4. **State Update** — Daemon updates `PUBLISH.md` with timestamp and status

## Docker Deployment

Each site has a dedicated Compose service that mounts:
- `vault_dir` — The synced Obsidian vault
- `repo_dir` — The cloned Hugo repository
- `/.ssh/id_ed25519` — Deploy key for Git operations

### Example Compose Entry

```yaml
markgrovesus-publisher:
  build:
    context: .
    dockerfile: Dockerfile
  entrypoint: python3 scripts/markgroves_entrypoint.py --poll-interval 5
  volumes:
    - /opt/stacks/obsidian-sync/vaults/MarkGroves-US:/vault:ro
    - /opt/stacks/obsidian-sync/markgroves-repo:/repo
    - /opt/stacks/obsidian-sync/markgrovesus-ssh/id_ed25519:/.ssh/id_ed25519:ro
  environment:
    - GIT_SSH_COMMAND=ssh -i /.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
  restart: unless-stopped
```

## Configuration

### SyncConfig

```python
config = SyncConfig(
    vault_dir=Path("/vault"),
    repo_dir=Path("/repo"),
    ownership={
        "posts": "content/posts",        # Vault posts/ → Hugo content/posts/
        "pages": "content",               # Vault pages/*.md → Hugo content/*.md
        "links": "content/links",         # Vault links/ → Hugo content/links/
    },
    max_image_width=1800,
    image_quality=82,
)
```

### PublisherDaemon

```python
daemon = PublisherDaemon(
    config=config,
    publish_file=Path("/vault/PUBLISH.md"),
    preview_branch="preview",
    production_branch="main",
    poll_interval=5,  # seconds
)
daemon.run()
```

## Image Processing

- **Wikilink Conversion** — `![[image.png]]` → `![image.png](images/image.png)`
- **Optimization** — JPEG re-encode, max 1800px width, quality 82
- **Asset Relocation** — Vault images/attachments → Bundle `images/` subfolder

## Publishing State

The `PUBLISH.md` frontmatter tracks:

```yaml
---
action: idle | build-preview | publish-production
last_run: 2026-09-13 14:25:30
last_status: "Production published: a1b2c3d"
---
```

Edit the `action` field to trigger:
- `build-preview` → Sync & push to `preview`
- `publish-production` → Sync preview, commit, push to `main`

Daemon automatically resets to `idle` after completion or error.

## Development

### Testing Locally

```bash
python3 -m pytest tests/
```

### Updating Publisher Code

For both sites:
```bash
ssh workbench \
  'cd /opt/stacks/obsidian-sync && \
   git fetch origin main && \
   git checkout main && \
   git reset --hard origin/main && \
   docker compose restart nextmountain-publisher markgrovesus-publisher'
```

## Troubleshooting

### Daemon Crashes

Check logs:
```bash
ssh workbench \
  'cd /opt/stacks/obsidian-sync && \
   docker compose logs -f nextmountain-publisher'
```

### Git Permission Errors

Ensure deploy keys have correct permissions:
```bash
ssh workbench \
  'ls -la /opt/stacks/obsidian-sync/markgrovesus-ssh/id_ed25519'
# Should be: -rw-r--r--
```

### Sync Stalled

Check vault sync status and restart if needed:
```bash
ssh workbench \
  'cd /opt/stacks/obsidian-sync && \
   docker compose restart sync-markgrovesus'
```
