"""Resolve QQ runtime artifacts through the guard and verify PRIVATE storage."""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit

from qq_database import SIDECARS

ROOT = Path(__file__).resolve().parents[1]


def _run(argv):
    env = {name: value for name, value in os.environ.items()
           if name.upper() not in {'GIT_PAGER', 'GH_PAGER', 'PAGER'}}
    _check_environment(env)
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    try:
        p = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', timeout=20, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Private storage verification unavailable: '+argv[0]) from exc
    if p.returncode:
        raise RuntimeError('Private storage verification failed: '+argv[0])
    return p.stdout.strip()


def _check_environment(environment=None):
    """Allow inert hints; pagers are removed before captured subprocesses run."""
    inert_git = {'GIT_INDEX_FILE', 'GIT_PREFIX', 'GIT_OPTIONAL_LOCKS', 'GIT_PAGER'}
    for name in (os.environ if environment is None else environment):
        upper = name.upper()
        if ((upper.startswith('GIT_') and upper not in inert_git)
                or upper in {'GH_HOST', 'GH_REPO', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
                             'SSL_CERT_FILE', 'SSL_CERT_DIR', 'CURL_CA_BUNDLE', 'CURL_SSL_BACKEND'}):
            raise RuntimeError('Unsupported private-storage routing environment: '+name)


def _physical_path(path):
    """Keep DATA on ordinary, single-link files without resolving away aliases."""
    path = Path(path).expanduser().absolute()
    if any(part.lower() == '.git' or ':' in part or part in ('.', '..')
           or part.endswith((' ', '.')) for part in path.parts[1:]):
        raise RuntimeError('Ambiguous or reserved DATA path')
    for node in (path, *path.parents):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
            raise RuntimeError('DATA path contains a link or reparse alias')
        if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise RuntimeError('DATA path is not an ordinary file or directory')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise RuntimeError('DATA file has an unproved hardlink alias')
    return path


def _check_data_aliases(path):
    for suffix in ('', '.lock', *SIDECARS):
        _physical_path(Path(str(path)+suffix))


def _configuration(directory):
    raw = _run(['git', '-C', str(directory), 'config', '--includes', '--null', '--list'])
    entries = []
    for record in raw.split('\0'):
        if not record:
            continue
        key, separator, value = record.partition('\n')
        if not separator or not key:
            raise RuntimeError('Cannot parse private-storage Git configuration')
        key = key.lower()
        field = key.rsplit('.', 1)[-1]
        if (key in {'core.worktree', 'core.sshcommand', 'core.gitproxy', 'ssh.variant'}
                or key.startswith('http.')
                or key.startswith('remote.') and (field in {'uploadpack', 'receivepack', 'vcs'}
                                                   or field.startswith('proxy'))):
            raise RuntimeError('Unsupported private-storage Git routing configuration: '+key)
        entries.append((key, value))
    return entries


def _https_identity(remote):
    if any(character.isspace() or ord(character) < 32 for character in remote):
        raise RuntimeError('Invalid companion publication URL')
    parsed = urlsplit(remote)
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com'
            or parsed.query or parsed.fragment):
        raise RuntimeError('Unverified transport: configure canonical https://github.com/OWNER/REPO URLs; SSH is unsupported')
    name = parsed.path.removeprefix('/').removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*/[A-Za-z0-9_-][A-Za-z0-9_.-]*', name):
        raise RuntimeError('Invalid companion repository identity')
    return name


def _prove_publication(repo, configuration):
    remotes = _run(['git', '-C', str(repo), 'remote']).splitlines()
    if not remotes or len(remotes) != len(set(remotes)) or any(
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', remote) for remote in remotes):
        raise RuntimeError('Companion requires verifiable named publication remotes')
    for key, value in configuration:
        if key == 'remote.pushdefault' or key.startswith('branch.') and key.endswith(('.remote', '.pushremote')):
            if value not in remotes:
                raise RuntimeError('Selected publication remote is missing or unsupported')
    identities = set()
    for remote in remotes:
        for mode in ([], ['--push']):
            urls = _run(['git', '-C', str(repo), 'remote', 'get-url', *mode, '--all', remote]).splitlines()
            if not urls:
                raise RuntimeError('Publication destination is missing or unknown')
            identities.update(_https_identity(url) for url in urls)
    for name in sorted(identities):
        if _run(['gh', 'api', '--hostname', 'github.com', 'repos/'+name, '--jq', '.private']) != 'true':
            raise RuntimeError('Companion publication destination is PUBLIC or visibility is unknown')


def private_path(requested):
    _check_environment()
    for selector in ('QQ_HISTORY_EXPORT_DATA_DIR', 'QQ_HISTORY_EXPORT_CONFIG', 'QQ_HISTORY_EXPORT_CONFIG_DIR'):
        value = os.environ.get(selector)
        if value:
            if not _physical_path(value).is_dir():
                raise RuntimeError('Explicit private storage selector does not exist: '+selector)
            break
    module_path = ROOT/'guards/tools/datadir.py'
    _physical_path(module_path)
    if not module_path.is_file():
        raise RuntimeError('Missing guards; initialize pinned submodules before using runtime tools')
    spec = importlib.util.spec_from_file_location('qq_guard_datadir', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.resolve_data_dir('qq-history-export')
    if base is None:
        raise RuntimeError('Uninitialized: set QQ_HISTORY_EXPORT_CONFIG to a PRIVATE companion clone with data/')
    base = _physical_path(base).resolve()
    if not base.is_dir():
        raise RuntimeError('Resolved private data directory does not exist')
    path = Path(requested).expanduser()
    path = path if path.is_absolute() else base/path
    path = _physical_path(path).resolve()
    _check_data_aliases(path)
    if not path.is_relative_to(base) or base.is_relative_to(ROOT) or ROOT.is_relative_to(base):
        raise RuntimeError('Output must stay inside the separate private data directory')
    existing = path
    while not existing.exists():
        existing = existing.parent
    if existing.is_file():
        existing = existing.parent
    configuration = _configuration(existing)
    repo = _physical_path(_run(['git', '-C', str(existing), 'rev-parse', '--show-toplevel'])).resolve()
    if not base.is_relative_to(repo) or repo.is_relative_to(ROOT) or ROOT.is_relative_to(repo):
        raise RuntimeError('Output requires a separate versioned PRIVATE companion')
    _prove_publication(repo, configuration)
    return path


def reject_input_alias(output, inputs, *, database=None):
    """Reserve inputs and SQLite sidecars against outputs and their fixed lock paths."""
    output = Path(output).resolve()
    protected = [Path(path).resolve() for path in inputs]
    if database is not None:
        source = Path(database).resolve()
        protected.extend(Path(str(source)+suffix) for suffix in SIDECARS)
    for candidate in (output, output.with_name(output.name+'.lock')):
        for source in protected:
            if candidate == source or (candidate.exists() and source.exists() and candidate.samefile(source)):
                raise ValueError('output or transaction lock aliases a database/input sidecar')


class OutputCleanupError(RuntimeError):
    """An explicit commit-boundary receipt when transaction cleanup needs intervention."""

    def __init__(self, path, committed, failures, cause):
        self.receipt = dict(status='committed_cleanup_required' if committed else 'failed_cleanup_required',
                            committed=committed, output=str(path),
                            cleanup_paths=[str(item) for item, _ in failures],
                            cleanup_error_types=[type(exc).__name__ for _, exc in failures],
                            failure_type=type(cause).__name__ if cause else None)
        super().__init__(self.receipt['status']+': '+str(path))


@contextmanager
def atomic_output(path):
    """Exclusive writer with distinct uncommitted and committed cleanup failures."""
    path = Path(path)
    _check_data_aliases(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name+'.lock')
    lock_stream = lock.open('x', encoding='utf-8')
    temporary = None
    committed = False
    failure = None
    try:
        with lock_stream as stream:
            stream.write('QQ output transaction in progress\n')
        fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', suffix='.partial', dir=path.parent)
        temporary = Path(name)
        os.close(fd)
        yield temporary
        _physical_path(temporary)
        _check_data_aliases(path)
        os.replace(temporary, path)
        committed = True
    except BaseException as exc:
        failure = exc
        raise
    finally:
        cleanup_failures = []
        for item in (temporary, lock):
            try:
                if item is not None and item.exists():
                    item.unlink()
            except OSError as exc:
                cleanup_failures.append((item, exc))
        if cleanup_failures:
            raise OutputCleanupError(path, committed, cleanup_failures, failure) from (
                failure or cleanup_failures[0][1])


def write_bundle(path, bundle):
    path = private_path(path)
    with atomic_output(path) as temporary:
        temporary.write_text(json.dumps(bundle, ensure_ascii=True, indent=2)+'\n', encoding='utf-8')
        if private_path(path) != path:
            raise ValueError('evidence destination changed before promotion')
    return path
