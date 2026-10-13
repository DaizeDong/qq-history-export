"""Storage discovery rejects undeclared roots before accessing a device or writing."""
import json
import os
import subprocess

import pytest

import make_fixtures as F
import qq_pull
import qq_storage


@pytest.mark.parametrize('selector', ['QQ_HISTORY_EXPORT_CONFIG', 'QQ_HISTORY_EXPORT_CONFIG_DIR'])
def test_config_without_data_child_is_uninitialized(selector, tmp_path, monkeypatch):
    tool, repo, base = F.build_storage_fixture(tmp_path)
    (tool / 'guards/tools/datadir.py').write_bytes(
        (qq_storage.ROOT / 'guards/tools/datadir.py').read_bytes())
    base.rmdir()
    monkeypatch.setattr(os, 'environ', {selector: str(repo)})
    monkeypatch.setattr(qq_storage, 'ROOT', tool)
    calls = []
    monkeypatch.setattr(qq_pull, 'adb', lambda *args: calls.append(args))
    with pytest.raises(RuntimeError, match='data/'):
        qq_pull.pull_database('', F.OWNER, 'qq_db_pull/candidate.db')
    assert calls == []
    assert not (repo / 'qq_db_pull').exists()


@pytest.mark.parametrize('selected', ['root', 'alternate'])
def test_data_override_must_use_declared_companion_data(selected, tmp_path, monkeypatch):
    tool, repo, base = F.build_storage_fixture(tmp_path)
    (tool / 'guards/tools/datadir.py').write_bytes(
        (qq_storage.ROOT / 'guards/tools/datadir.py').read_bytes())
    target = repo if selected == 'root' else repo / 'exports'
    target.mkdir(exist_ok=True)
    monkeypatch.setattr(os, 'environ', {'QQ_HISTORY_EXPORT_DATA_DIR': str(target)})
    monkeypatch.setattr(qq_storage, 'ROOT', tool)
    with pytest.raises(RuntimeError, match='data/'):
        qq_storage.private_path('qq_db_pull/candidate.db')
    assert not (target / 'qq_db_pull').exists()


@pytest.fixture
def plain_storage(tmp_path, monkeypatch):
    """A plain companion data/ directory: no Git, no remote, no visibility receipt."""
    tool, repo, base = F.build_storage_fixture(tmp_path)
    monkeypatch.setattr(qq_storage, 'ROOT', tool)
    monkeypatch.setattr(os, 'environ', {'QQ_HISTORY_EXPORT_DATA_DIR': str(base)})
    return repo, base


def test_write_is_path_only_and_runs_no_process(plain_storage, monkeypatch):
    _, data = plain_storage

    def no_process(*args, **kwargs):
        raise AssertionError('storage resolution must not run Git or gh')

    monkeypatch.setattr(subprocess, 'run', no_process)
    monkeypatch.setattr(subprocess, 'check_output', no_process)
    path = qq_storage.write_bundle('qq_keys/evidence.json', {'synthetic': True})
    assert path == data.resolve() / 'qq_keys' / 'evidence.json'
    assert json.loads(path.read_text(encoding='utf-8')) == {'synthetic': True}
    assert sorted(p.name for p in path.parent.iterdir()) == ['evidence.json']


def test_data_dir_inside_source_tree_is_refused(tmp_path, monkeypatch):
    tool, _, _ = F.build_storage_fixture(tmp_path)
    inside = tool / 'data'
    inside.mkdir()
    monkeypatch.setattr(qq_storage, 'ROOT', tool)
    (tool / 'guards/tools/datadir.py').write_text(
        'from pathlib import Path\ndef resolve_data_dir(name):\n    return Path(' + repr(str(inside)) + ')\n',
        encoding='utf-8')
    monkeypatch.setattr(os, 'environ', {})
    with pytest.raises(RuntimeError, match='outside this source'):
        qq_storage.private_path('qq_keys/evidence.json')
    assert list(inside.iterdir()) == []


def test_git_metadata_destination_is_refused(plain_storage):
    _, data = plain_storage
    with pytest.raises(RuntimeError, match='reserved'):
        qq_storage.private_path('.git/evidence.json')
    assert list(data.iterdir()) == []


def test_missing_companion_refuses_before_device(tmp_path, monkeypatch):
    tool, _, base = F.build_storage_fixture(tmp_path)
    base.rmdir()
    monkeypatch.setattr(qq_storage, 'ROOT', tool)
    monkeypatch.setattr(os, 'environ', {})
    monkeypatch.setattr(qq_pull, 'adb', lambda *args: pytest.fail('missing companion reached device'))
    with pytest.raises(RuntimeError, match='does not exist'):
        qq_pull.pull_database('', F.OWNER, 'qq_db_pull/candidate.db')
    assert not base.exists()
