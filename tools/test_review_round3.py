"""PRIVATE proof regressions using generated trust environments and inert process seams."""
import json
import os
import subprocess
import sys

import pytest

import make_fixtures as F
import qq_decode as D
import qq_keyfind as K
import qq_pull as P
import qq_storage as S


@pytest.fixture
def visibility_proofs():
    return []


@pytest.fixture
def companion(tmp_path, monkeypatch, visibility_proofs):
    tool, repo, base = F.build_storage_fixture(tmp_path)
    scenario = F.storage_routes()['private']
    calls = []
    device_calls = []
    monkeypatch.setattr(os, 'environ', {})
    for key, value in F.storage_https_positive_environments()['pager'].items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('QQ_HISTORY_EXPORT_DATA_DIR', str(base))
    monkeypatch.setattr(S, 'ROOT', tool)

    def run(argv, **kwargs):
        calls.append({'argv': list(argv), 'environment': dict(kwargs['env'])})
        if argv[0] == 'gh':
            output = 'true'
        elif '--show-toplevel' in argv:
            output = str(repo)
        elif 'config' in argv:
            output = ''
        elif argv[-1] == 'remote':
            output = '\n'.join(scenario['remotes'])
        elif 'get-url' in argv:
            output = '\n'.join(scenario['remotes'][argv[-1]][
                'push' if '--push' in argv else 'fetch'])
        else:
            raise AssertionError('Unexpected synthetic proof command')
        return subprocess.CompletedProcess(argv, 0, output, '')

    def device(*args, **kwargs):
        device_calls.append(True)
        raise AssertionError('Device or database execution must not be reached')

    monkeypatch.setattr(S.subprocess, 'run', run)
    # The live visibility answer comes from the pinned Guards kit (any logged-in gh account);
    # its own synthetic-gh tests live in test_visibility_any_gh_account.py.
    monkeypatch.setattr(S, '_github_private', lambda name: visibility_proofs.append(name) or 'true')
    monkeypatch.setattr(P, 'adb', device)
    monkeypatch.setattr(K, 'recover_key', device)
    monkeypatch.setattr(D, 'export_database', device)
    return base, calls, device_calls


@pytest.mark.parametrize('case', F.storage_https_environment_cases(), ids=lambda row: row['id'])
@pytest.mark.parametrize('entrypoint', ['resolve', 'bundle', 'pull', 'recover', 'decode'])
def test_trust_override_refuses_before_proof_device_or_creation(case, entrypoint, companion, monkeypatch, capsys):
    base, calls, device_calls = companion
    monkeypatch.setenv(case['name'], case['value'])
    output = 'nested/evidence.json'
    if entrypoint in ('recover', 'decode'):
        argv = ['qq_' + ('keyfind' if entrypoint == 'recover' else 'decode') + '.py',
                '--db', 'candidate.db', '--out', output]
        if entrypoint == 'recover':
            argv += ['--owner', F.OWNER]
            main = K.main
        else:
            argv += ['--evidence', 'key.json']
            main = D.main
        monkeypatch.setattr(sys, 'argv', argv)
        assert main() == 1
        captured = capsys.readouterr()
        assert 'environment' in captured.err.lower()
        assert case['name'] in captured.err
        assert not captured.out
    else:
        with pytest.raises(RuntimeError, match=case['name']):
            if entrypoint == 'resolve':
                S.private_path(output)
            elif entrypoint == 'bundle':
                S.write_bundle(output, {'synthetic': True})
            else:
                P.pull_database('', F.OWNER, output)
    assert calls == []
    assert device_calls == []
    assert list(base.iterdir()) == []


@pytest.mark.parametrize('case', F.storage_https_environment_cases(), ids=lambda row: row['id'])
def test_proof_subprocess_rechecks_trust_environment(case, companion, monkeypatch):
    _, calls, _ = companion
    S._check_environment()
    monkeypatch.setenv(case['name'], case['value'])
    with pytest.raises(RuntimeError, match=case['name']):
        S._run(['gh', 'api', '--hostname', 'github.com',
                'repos/example-owner/synthetic-private', '--jq', '.private'])
    assert calls == []


@pytest.mark.parametrize('name,environment', F.storage_https_positive_environments().items())
def test_default_and_inert_authenticated_environment_remain_supported(name, environment, companion, monkeypatch,
                                                                       visibility_proofs):
    base, calls, device_calls = companion
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    output = S.write_bundle('nested/evidence.json', {'synthetic': True})
    assert json.loads(output.read_text(encoding='utf-8')) == {'synthetic': True}
    assert visibility_proofs
    for row in calls:
        assert all(row['environment'][key] == value for key, value in environment.items()
                   if key not in {'GIT_OPTIONAL_LOCKS', 'GIT_PAGER', 'GH_PAGER', 'PAGER'})
        assert not {'GIT_PAGER', 'GH_PAGER', 'PAGER'} & row['environment'].keys()
        assert row['environment']['GIT_OPTIONAL_LOCKS'] == '0'
        assert row['environment']['GIT_TERMINAL_PROMPT'] == '0'
    assert all(os.environ[key] == value for key, value in environment.items())
    assert device_calls == []
    assert not list(base.rglob('*.lock')) and not list(base.rglob('*.partial'))
