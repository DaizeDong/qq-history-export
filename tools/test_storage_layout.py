"""Storage discovery rejects undeclared roots before accessing a device or writing."""
import os
import json
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
    monkeypatch.setattr(qq_storage, '_configuration', lambda path: [])
    monkeypatch.setattr(qq_storage, '_run', lambda args: str(repo))
    monkeypatch.setattr(qq_storage, '_prove_publication', lambda *args: None)
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
    monkeypatch.setattr(qq_storage, '_configuration', lambda path: [])
    monkeypatch.setattr(qq_storage, '_run', lambda args: str(repo))
    monkeypatch.setattr(qq_storage, '_prove_publication', lambda *args: None)
    with pytest.raises(RuntimeError, match='data/'):
        qq_storage.private_path('qq_db_pull/candidate.db')
    assert not (target / 'qq_db_pull').exists()


@pytest.fixture
def native_storage(tmp_path, monkeypatch):
    repo, data, environment = F.build_versioned_storage(tmp_path)
    monkeypatch.setattr(os, 'environ', environment)
    # The shared admission proves all routes from its local receipt, without gh.
    monkeypatch.setattr(qq_storage, '_prove_publication', lambda *args: None)
    return repo, data


@pytest.mark.parametrize('relative', ['qq_keys/unknown.txt', 'other/evidence.json'])
def test_evidence_writer_refuses_undeclared_leaf(native_storage, relative):
    repo, data = native_storage
    with pytest.raises(ValueError, match='owner'):
        qq_storage.write_bundle(relative, {'synthetic': True})
    assert list(data.iterdir()) == []


def test_ignored_evidence_is_rejected_before_creation(native_storage):
    repo, data = native_storage
    (repo/'.gitignore').write_text('data/qq_keys/\n', encoding='utf-8')
    with pytest.raises(ValueError, match='ignored'):
        qq_storage.write_bundle('qq_keys/evidence.json', {'synthetic': True})
    assert list(data.iterdir()) == []


def test_declared_evidence_write_commits_complete_json(native_storage):
    _, data = native_storage
    path = qq_storage.write_bundle('qq_keys/evidence.json', {'synthetic': True})
    assert json.loads(path.read_text(encoding='utf-8')) == {'synthetic': True}
    assert sorted(p.name for p in path.parent.iterdir()) == ['evidence.json']


@pytest.mark.parametrize('backend', ['openssl', 'schannel'])
def test_standard_tls_backend_preserves_configuration_proof(tmp_path, monkeypatch, backend):
    monkeypatch.setattr(qq_storage, '_run', lambda args: 'http.sslbackend\n'+backend+'\0')
    assert qq_storage._configuration(tmp_path) == [('http.sslbackend', backend)]


@pytest.mark.parametrize('record', [
    'http.sslbackend\nunknown\0', 'http.sslverify\nfalse\0',
    'http.https://github.com.sslbackend\nschannel\0',
])
def test_backend_allowance_does_not_admit_other_tls_overrides(tmp_path, monkeypatch, record):
    monkeypatch.setattr(qq_storage, '_run', lambda args: record)
    with pytest.raises(RuntimeError, match='configuration'):
        qq_storage._configuration(tmp_path)


def test_native_custom_ca_stays_rejected(native_storage):
    repo, data = native_storage
    subprocess.run(['git', '-C', str(repo), 'config', 'http.sslcainfo',
                    str(repo/'custom-ca.pem')], check=True, capture_output=True)
    with pytest.raises(RuntimeError, match='PRIVATE|HTTP|trust'):
        qq_storage.write_bundle('qq_keys/evidence.json', {'synthetic': True})
    assert list(data.iterdir()) == []


def test_pull_wrong_artifact_type_is_rejected_before_device(native_storage, monkeypatch):
    _, data = native_storage
    monkeypatch.setattr(qq_pull, 'adb', lambda *args: pytest.fail('undeclared output reached device'))
    with pytest.raises(ValueError, match='producer'):
        qq_pull.pull_database('', F.OWNER, 'qq_keys/evidence.json')
    assert list(data.iterdir()) == []


@pytest.mark.parametrize('ignored', ['data/qq_keys/evidence.json.lock', 'data/qq_keys/.*.partial'])
def test_transaction_paths_are_admitted_before_any_creation(native_storage, ignored):
    repo, data = native_storage
    (repo / '.gitignore').write_text(ignored + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match='ignored'):
        qq_storage.write_bundle('qq_keys/evidence.json', {'synthetic': True})
    assert not (data / 'qq_keys').exists()


@pytest.mark.skipif(os.name != 'nt', reason='NTFS short-name control')
def test_existing_short_name_is_not_resolved_before_admission(native_storage):
    import ctypes
    from pathlib import Path
    _, data = native_storage
    target = data / 'qq_keys' / 'synthetic-long-evidence-name.json'
    target.parent.mkdir()
    target.write_text('{}', encoding='utf-8')
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(target), buffer, len(buffer)):
        pytest.skip('short names unavailable')
    alias = target.parent / Path(buffer.value).name
    if alias.name.casefold() == target.name.casefold():
        pytest.skip('short names disabled for this volume')
    with pytest.raises((RuntimeError, ValueError)):
        qq_storage.private_path(alias, artifact_id='recovery_evidence')
    assert target.read_text(encoding='utf-8') == '{}'
