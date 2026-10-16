"""Resolve QQ runtime artifacts inside the companion data/ directory (path-only checks)."""
from contextlib import contextmanager
from functools import lru_cache
import json
import os
from pathlib import Path
import stat
import uuid

from qq_database import SIDECARS

ROOT = Path(__file__).resolve().parents[1]


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


_SELECTORS = ('QQ_HISTORY_EXPORT_DATA_DIR', 'QQ_HISTORY_EXPORT_CONFIG')


@lru_cache(maxsize=None)
def _resolver(root):
    try:
        from fleet_guards.runtime import companion_resolver
    except ImportError as exc:
        raise RuntimeError('fleet_guards is not installed; run: pip install -e "$(git config --get fleet.guards)"') from exc
    return companion_resolver(source_root=root)


@lru_cache(maxsize=None)
def _data_base(root, selection):
    """The companion data/ directory, resolved and checked once per tool root and selector values."""
    base = _resolver(root).resolve_data_dir('qq-history-export')
    if base is None:
        raise RuntimeError('Uninitialized: set QQ_HISTORY_EXPORT_CONFIG to a private companion clone with data/')
    base = _physical_path(base).resolve()
    if not base.is_dir():
        raise RuntimeError('Resolved private data directory does not exist')
    if base.name != 'data':
        raise RuntimeError('Storage must use the companion data/ directory declared in storage.contract.json')
    if base.is_relative_to(root) or root.is_relative_to(base):
        raise RuntimeError('Output requires a companion outside this source repository')
    return base


def private_path(requested):
    """Resolve a DATA path inside the companion data/ directory. Path-only: no Git or gh runs.

    Keeping DATA out of public repositories is enforced at commit and push time by the
    .githooks shims. Here the companion must already exist, the data directory must be named data/ and
    sit outside this source tree, and the result must stay inside it on ordinary files. The
    data directory is resolved once per process for each selector configuration.
    """
    base = _data_base(ROOT, tuple(os.environ.get(selector) for selector in _SELECTORS))
    path = Path(requested).expanduser()
    path = path if path.is_absolute() else base/path
    path = _physical_path(path).resolve()
    _check_data_aliases(path)
    if not path.is_relative_to(base):
        raise RuntimeError('Output must stay inside the separate private data directory')
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
    lock = private_path(path.with_name(path.name+'.lock'))
    temporary = private_path(path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.partial'))
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = lock.open('x', encoding='utf-8')
    temporary_created = False
    committed = False
    failure = None
    try:
        with lock_stream as stream:
            stream.write('QQ output transaction in progress\n')
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        temporary_created = True
        os.close(fd)
        yield temporary
        private_path(temporary)
        _check_data_aliases(path)
        os.replace(temporary, path)
        committed = True
    except BaseException as exc:
        failure = exc
        raise
    finally:
        cleanup_failures = []
        for item in (temporary if temporary_created else None, lock):
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
    return path
