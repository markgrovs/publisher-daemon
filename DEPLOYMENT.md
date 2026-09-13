# Deploying Publisher-Daemon to Workbench

## Prerequisites

- `publisher-daemon` repo cloned to Workbench
- Both `nextmountainoverland` and `markgroves.us` Hugo repos cloned at `/opt/stacks/obsidian-sync/blog-repo` and `/opt/stacks/obsidian-sync/markgroves-repo`
- Obsidian Sync vaults running and fully synced
- SSH deploy keys in place:
  - `/opt/stacks/obsidian-sync/publisher-ssh/id_ed25519` (NextMountain-Blog)
  - `/opt/stacks/obsidian-sync/markgrovesus-ssh/id_ed25519` (MarkGroves.us)

## Step 1: Clone publisher-daemon to Workbench

```bash
ssh workbench
cd /opt/stacks/obsidian-sync
git clone https://github.com/markgrovs/publisher-daemon.git
```

## Step 2: Update docker-compose.yml

Merge `docker-compose.snippet.yml` into the main Compose stack:

```bash
# On Workbench
cd /opt/stacks/obsidian-sync
# Manually add the nextmountain-publisher and markgrovesus-publisher services
# from docker-compose.snippet.yml to docker-compose.yml
# (or use yq/jq if you prefer)
```

Verify the services are defined:
```bash
docker compose config | grep -A 10 "nextmountain-publisher\|markgrovesus-publisher"
```

## Step 3: Build and Start

```bash
cd /opt/stacks/obsidian-sync
docker compose build nextmountain-publisher markgrovesus-publisher
docker compose up -d nextmountain-publisher markgrovesus-publisher
```

## Step 4: Verify Containers Are Running

```bash
docker compose ps | grep publisher
```

Expected output:
```
obsidian-sync-nextmountain-publisher-1    python3 scripts/nextmountain...   Up
obsidian-sync-markgrovesus-publisher-1    python3 scripts/markgroves...    Up
```

## Step 5: Check Initial Logs

```bash
docker compose logs -f nextmountain-publisher
docker compose logs -f markgrovesus-publisher
```

You should see:
```
[INFO] PublisherDaemon started
[INFO] Polling /vault/PUBLISH.md every 5 seconds
[INFO] Current state: action=idle
```

## Step 6: Test MarkGroves-US Pipeline

### On your Mac, in the MarkGroves-US vault:

1. Create a test post:
   ```
   posts/2026-09-13-publisher-test/
   ├── index.md (with frontmatter)
   └── images/test.jpg
   ```

2. Edit `PUBLISH.md` frontmatter:
   ```yaml
   action: build-preview
   ```

3. Watch the daemon logs on Workbench:
   ```bash
   docker compose logs -f markgrovesus-publisher
   ```

   You should see:
   ```
   [INFO] Action detected: build-preview
   [INFO] Syncing vault...
   [INFO] Processing posts/2026-09-13-publisher-test/index.md
   [INFO] Processing images...
   [INFO] Committing to preview branch
   [INFO] Pushing to origin/preview
   [SUCCESS] Preview published
   ```

4. Check Netlify for the branch deploy preview (under `Deploy previews`)

5. Once verified, edit `PUBLISH.md` again:
   ```yaml
   action: publish-production
   ```

6. Watch for production push to `main` branch and live Netlify build.

## Troubleshooting

### Daemon crashes immediately

Check logs for Python errors:
```bash
docker compose logs nextmountain-publisher
```

Common issues:
- Missing module imports → rebuild image
- Vault not synced → check `sync-nextmountainblog` status
- Git SSH key not readable → check permissions

### Git permission denied

Verify SSH key is readable by the container:
```bash
ssh workbench
ls -la /opt/stacks/obsidian-sync/markgrovesus-ssh/id_ed25519
# Should be: -rw-r--r-- (or at least readable by root)
```

If not, fix permissions:
```bash
chmod 644 /opt/stacks/obsidian-sync/markgrovesus-ssh/id_ed25519
```

### Vault changes not picked up

Ensure Obsidian Sync is fully synced:
```bash
docker compose logs sync-markgrovesus | tail -20
# Should show "Fully synced"
```

If stalled, restart:
```bash
docker compose restart sync-markgrovesus
```

## Updating Publisher-Daemon Code

Once deployed, to pull updates from GitHub:

```bash
ssh workbench
cd /opt/stacks/obsidian-sync/publisher-daemon
git fetch origin main
git checkout main
git reset --hard origin/main
cd ..
docker compose build nextmountain-publisher markgrovesus-publisher
docker compose up -d nextmountain-publisher markgrovesus-publisher
```

## Rollback

To stop publishers and revert to the old system:

```bash
docker compose down nextmountain-publisher markgrovesus-publisher
# Publishers stop, old scripts still available on disk
```
