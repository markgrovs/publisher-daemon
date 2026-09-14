"""
Unit tests for vault→repo mirror sync semantics.

Covers: post bundle writing, flat file sync, draft-flag preservation,
manifest-based pruning (vault deletions propagate), and the safety
guarantee that legacy repo files never in the manifest are untouched.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publisher.sync import (
    SyncConfig,
    sync_owned,
    find_post_markdown,
    is_draft,
    MANIFEST_NAME,
)


@pytest.fixture
def env(tmp_path):
    """Vault + repo skeleton with standard ownership map."""
    vault = tmp_path / "vault"
    repo = tmp_path / "repo"
    for d in ("posts", "pages", "links"):
        (vault / d).mkdir(parents=True)
    repo.mkdir()
    config = SyncConfig(
        vault_dir=vault,
        repo_dir=repo,
        ownership={"posts": "content/posts", "pages": "content", "links": "content/links"},
    )
    return config


def write_post(vault: Path, name: str, body: str = "Hello", draft: bool = False):
    post_dir = vault / "posts" / name
    post_dir.mkdir(parents=True, exist_ok=True)
    fm = "---\ntitle: Test\ndraft: true\n---\n" if draft else "---\ntitle: Test\n---\n"
    (post_dir / "index.md").write_text(fm + body, encoding="utf-8")
    return post_dir


def manifest_paths(repo: Path) -> list:
    m = repo / MANIFEST_NAME
    if not m.exists():
        return []
    return json.loads(m.read_text())["paths"]


# ---------- find_post_markdown ----------

def test_find_post_markdown_prefers_index(env):
    d = write_post(env.vault_dir, "2026-01-01-a")
    assert find_post_markdown(d).name == "index.md"


def test_find_post_markdown_falls_back_to_sole_md(env):
    d = env.vault_dir / "posts" / "2026-01-01-b"
    d.mkdir(parents=True)
    (d / "index.md.md").write_text("---\ntitle: x\n---\nbody", encoding="utf-8")
    assert find_post_markdown(d).name == "index.md.md"


def test_find_post_markdown_none_with_two_md(env):
    d = env.vault_dir / "posts" / "2026-01-01-c"
    d.mkdir(parents=True)
    (d / "a.md").write_text("x", encoding="utf-8")
    (d / "b.md").write_text("y", encoding="utf-8")
    assert find_post_markdown(d) is None


# ---------- is_draft ----------

def test_is_draft_true_variants(env):
    d = env.vault_dir / "posts" / "tmp"
    d.mkdir(parents=True)
    for val in ("true", "True", "yes"):
        f = d / f"{val}.md"
        f.write_text(f"---\ndraft: {val}\n---\n", encoding="utf-8")
        assert is_draft(f), val


def test_is_draft_false_when_absent_or_no(env):
    d = env.vault_dir / "posts" / "tmp2"
    d.mkdir(parents=True)
    f1 = d / "none.md"
    f1.write_text("---\ntitle: x\n---\n", encoding="utf-8")
    assert not is_draft(f1)
    f2 = d / "no.md"
    f2.write_text("---\ndraft: no\n---\n", encoding="utf-8")
    assert not is_draft(f2)


# ---------- mirror semantics ----------

def test_post_bundle_written_with_draft_flag_intact(env):
    write_post(env.vault_dir, "2026-01-01-draft-post", draft=True)
    touched = sync_owned(env, include_drafts=True)
    out = env.repo_dir / "content/posts/2026-01-01-draft-post/index.md"
    assert out.exists()
    assert "draft: true" in out.read_text(encoding="utf-8")
    assert any(p.name == "2026-01-01-draft-post" for p in touched)


def test_flat_files_synced(env):
    (env.vault_dir / "pages/cv.md").write_text("---\ntitle: CV\n---\nBio", encoding="utf-8")
    (env.vault_dir / "links/data.md").write_text("---\ntitle: L\n---\nlink", encoding="utf-8")
    sync_owned(env, include_drafts=True)
    assert (env.repo_dir / "content/cv.md").exists()
    assert (env.repo_dir / "content/links/data.md").exists()


def test_deletion_in_vault_prunes_repo(env):
    write_post(env.vault_dir, "2026-01-01-gone")
    sync_owned(env, include_drafts=True)
    assert (env.repo_dir / "content/posts/2026-01-01-gone/index.md").exists()

    # Delete from vault, sync again
    import shutil
    shutil.rmtree(env.vault_dir / "posts/2026-01-01-gone")
    touched = sync_owned(env, include_drafts=True)
    assert not (env.repo_dir / "content/posts/2026-01-01-gone").exists()
    assert any("2026-01-01-gone" in str(p) for p in touched)


def test_flat_file_deletion_prunes_repo(env):
    (env.vault_dir / "pages/cv.md").write_text("---\ntitle: CV\n---\n", encoding="utf-8")
    sync_owned(env, include_drafts=True)
    assert (env.repo_dir / "content/cv.md").exists()

    (env.vault_dir / "pages/cv.md").unlink()
    sync_owned(env, include_drafts=True)
    assert not (env.repo_dir / "content/cv.md").exists()


def test_legacy_files_never_in_manifest_are_untouched(env):
    # Legacy file in repo that the daemon never wrote
    legacy = env.repo_dir / "content/posts/2019-old-post"
    legacy.mkdir(parents=True)
    (legacy / "index.md").write_text("old content", encoding="utf-8")

    write_post(env.vault_dir, "2026-01-01-new")
    sync_owned(env, include_drafts=True)
    # Sync again with the vault post deleted — legacy must survive
    import shutil
    shutil.rmtree(env.vault_dir / "posts/2026-01-01-new")
    sync_owned(env, include_drafts=True)

    assert (legacy / "index.md").exists()
    assert "2019-old-post" not in manifest_paths(env.repo_dir)


def test_manifest_records_written_paths(env):
    write_post(env.vault_dir, "2026-01-01-x")
    (env.vault_dir / "pages/now.md").write_text("---\ntitle: Now\n---\n", encoding="utf-8")
    sync_owned(env, include_drafts=True)
    paths = manifest_paths(env.repo_dir)
    assert "content/posts/2026-01-01-x" in paths
    assert "content/now.md" in paths


def test_idempotent_second_sync_no_touched_prunes(env):
    write_post(env.vault_dir, "2026-01-01-y")
    first = sync_owned(env, include_drafts=True)
    second = sync_owned(env, include_drafts=True)
    # Second sync rewrites (idempotent content) but prunes nothing
    prunes = [p for p in second if not p.exists()]
    assert not prunes
    assert (env.repo_dir / "content/posts/2026-01-01-y/index.md").exists()


def test_include_drafts_false_skips_drafts(env):
    write_post(env.vault_dir, "2026-01-01-drafty", draft=True)
    sync_owned(env, include_drafts=False)
    assert not (env.repo_dir / "content/posts/2026-01-01-drafty").exists()
