# Next Mountain authoring

The Next Mountain entrypoint enables the Field Notebook adapter. Other sites retain their existing sync behavior. Rebuild and redeploy the daemon image to activate this code; editing this checkout does not update a running service.

Paths are relative to the vault mounted at `/vault`:

| Vault source | Hugo destination | Purpose |
| --- | --- | --- |
| `posts/<slug>/index.md` | `content/posts/<slug>/index.md` | Journal, including daily notes and long stories |
| `cairns/<slug>/index.md` | `content/cairns/<slug>/index.md` | Reviews and lessons |
| `journeys/<slug>/_index.md` | `content/journeys/<slug>/_index.md` | Trip introductions |
| `home/index.md` | `content/home/index.md` | Stable homepage welcome and photos |
| `pages/*.md` | `content/*.md` | Existing standalone pages |
| `drafts/*.md` | `content/drafts/*.md` | Legacy drafts |

Posts, Cairns and Journeys also accept a flat `<slug>.md` or a folder containing one Markdown file. Use lowercase stable slugs. Daily notes can omit `title`; provide `date`, `lat`, `long`, `location`, and `journeys: [trip-slug]`. Longer stories and Cairns can retain titles. YAML lists and nested photo settings are preserved. Empty coordinates are accepted; supplied coordinates must be a valid pair.

Use `thumbnail: photo.jpg` on Journeys/Cairns. The homepage uses `home_photos`, a list of up to two mappings with `src`, author-written `alt`, and optional `caption`. It is published as a headless bundle consumed by the theme.

Reference delivery images with Markdown or Obsidian image embeds. Local resources resolve beside the note or under `attachments/`. Only referenced assets are copied; images are resized and re-encoded. Local PDF/GPX/text downloads and explicitly prepared MP4 clips are supported. Markdown links to other pages should use their site URL, such as `/dispatches/day/`. Flat legacy pages retain their existing text-copy behavior. Keep private originals outside these source paths. Prepare video delivery copies separately; the adapter does not transcode them.

Validation and media preparation finish in temporary staging before repository content changes. The manifest tracks generated files and prunes removed owned files while retaining unrelated content. Existing directory manifests migrate to file ownership on the first successful sync. Back up the deployed manifest and state before deployment. Drafts remain in Git and are visible in the public preview. This integration does not enable POSSE.
