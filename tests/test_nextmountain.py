from pathlib import Path
import pytest
from PIL import Image
from publisher.nextmountain import create_config, metadata
from publisher.sync import sync_owned


def test_content_routes_metadata_and_pruning(tmp_path):
    vault, repo = tmp_path/'vault', tmp_path/'repo'
    config = create_config(vault, repo)
    for section, index in [('posts','index.md'), ('cairns','index.md'), ('journeys','_index.md')]:
        folder = vault/section/'florida'
        folder.mkdir(parents=True)
        (folder/index).write_text('---\ndate: 2026-10-31\nlat: 0\nlong: -90.57\nlocation: Clarksdale, MS\njourneys: [florida]\ndraft: true\n---\nHello')
    home = vault/'home'
    home.mkdir()
    Image.new('RGB', (20,20)).save(home/'photo.jpg')
    (home/'index.md').write_text('---\nhome_photos:\n  - src: photo.jpg\n    alt: A campsite\n---\nWelcome')
    sync_owned(config)
    data, _ = metadata((repo/'content/posts/florida/index.md').read_text())
    assert data['journeys'] == ['florida'] and data['lat'] == 0
    assert 'title' not in data
    assert (repo/'content/journeys/florida/_index.md').exists()
    data, _ = metadata((repo/'content/home/index.md').read_text())
    assert data['headless'] is True
    assert (repo/'content/home'/data['home_photos'][0]['src']).exists()
    legacy = repo/'content/posts/legacy.md'
    legacy.write_text('legacy')
    (vault/'posts/florida/index.md').unlink()
    (vault/'posts/florida').rmdir()
    sync_owned(config)
    assert not (repo/'content/posts/florida/index.md').exists()
    assert legacy.read_text() == 'legacy'


def test_invalid_input_leaves_repository_untouched(tmp_path):
    vault, repo = tmp_path/'vault', tmp_path/'repo'
    folder = vault/'posts/day'
    folder.mkdir(parents=True)
    source = folder/'index.md'
    source.write_text('---\nlat: 0\nlong: 0\n---\nOriginal')
    config = create_config(vault, repo)
    sync_owned(config)
    snapshot = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()}
    source.write_text('---\nlat: 91\nlong: 0\n---\nInvalid')
    with pytest.raises(ValueError):
        sync_owned(config)
    assert snapshot == {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob('*') if p.is_file()}


@pytest.mark.parametrize('section,index', [('posts','index.md'), ('cairns','index.md'), ('journeys','_index.md')])
def test_folder_notes_and_attachment_directories(tmp_path, section, index):
    vault, repo = tmp_path/'vault', tmp_path/'repo'
    bundle = vault/section/'test-post-memphis'
    bundle.mkdir(parents=True)
    (bundle/'test-post-memphis.md').write_text('---\ndraft: true\n---\n![A stop](photo.jpg)')
    Image.new('RGB', (20,20)).save(bundle/'photo.jpg')
    images = vault/section/'images'
    images.mkdir()
    Image.new('RGB', (20,20)).save(images/'unreferenced.jpg')
    sync_owned(create_config(vault, repo))
    output = repo/'content'/section/'test-post-memphis'
    assert (output/index).exists()
    assert len(list((output/'media').glob('*.jpg'))) == 1
    assert not (repo/'content'/section/'images').exists()


def test_nested_notes_are_not_silently_skipped(tmp_path):
    vault, repo = tmp_path/'vault', tmp_path/'repo'
    nested = vault/'posts/organizer/day'
    nested.mkdir(parents=True)
    (nested/'day.md').write_text('---\ndraft: true\n---\nNote')
    with pytest.raises(ValueError, match='Nested notes'):
        sync_owned(create_config(vault, repo))
