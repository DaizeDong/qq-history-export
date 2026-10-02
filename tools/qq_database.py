"""Read-only classic QQ schema and snapshot checks, without decoding claims."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

TABLE = re.compile(r'mr_(friend|troop)_[A-Fa-f0-9]{32}_New')
FIELDS = {'issend', 'msgData', 'senderuin', 'selfuin', 'frienduin', 'time', 'uniseq', 'msgtype'}
SIDECARS = ('-wal', '-journal', '-shm')


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def message_identity(value):
    """Classic Java long identity, validated before canonical string conversion."""
    if type(value) is int:
        number = value
    elif isinstance(value, str) and len(value) <= 20 and re.fullmatch(r'-?[0-9]+', value):
        number = int(value)
    else:
        raise ValueError('message uniseq identity must be a non-null integer')
    if not -(2**63) <= number < 2**63:
        raise ValueError('message uniseq identity is outside the signed 64-bit domain')
    return str(number)


def no_live_journal(path):
    for suffix in ('-wal', '-journal'):
        sidecar = Path(str(path)+suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ValueError('database has an active journal; provide a stable standalone snapshot')


@dataclass(frozen=True)
class DatabaseSnapshot:
    path: Path

    def __fspath__(self):
        return str(self.path)


@contextmanager
def standalone_snapshot(source):
    """Freeze bytes once, reuse them across stages, and reject source drift before return.

    Temporary bytes live beside the selected private input. Reentrant validation uses
    the existing snapshot. Complete this context before promoting any dependent output.
    """
    if isinstance(source, DatabaseSnapshot):
        yield source
        return
    source = Path(source).resolve()
    no_live_journal(source)
    before = sha256(source)
    with tempfile.TemporaryDirectory(prefix='.qq-snapshot-', dir=source.parent) as directory:
        snapshot = DatabaseSnapshot(Path(directory)/'snapshot.db')
        shutil.copyfile(source, snapshot)
        if sha256(snapshot) != before or sha256(source) != before:
            raise ValueError('database changed while freezing the snapshot')
        no_live_journal(source)
        yield snapshot
        no_live_journal(source)
        if sha256(source) != before or sha256(snapshot) != before:
            raise ValueError('database changed during snapshot processing')


@contextmanager
def open_database(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('database does not exist')
    no_live_journal(path)
    # Inputs are standalone snapshots. Immutable access also avoids creating WAL/SHM
    # files merely because a checkpointed file retained its WAL-mode header.
    db = sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        yield db
    except sqlite3.Error as exc:
        raise ValueError('invalid SQLite snapshot: '+type(exc).__name__) from exc
    finally:
        db.close()


def tables(cur):
    result = []
    for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        name = name.decode() if isinstance(name, bytes) else name
        if not name.startswith(('mr_friend', 'mr_troop')):
            continue
        match = TABLE.fullmatch(name)
        if not match:
            raise ValueError('unsupported classic QQ message table name')
        result.append((name, 'dm' if match.group(1) == 'friend' else 'group'))
    return sorted(result)


def inspect_database(path):
    with open_database(path) as db:
        if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        found = tables(db.cursor())
        if not found:
            raise ValueError('no supported classic QQ message tables; NT is unsupported')
        for name, _ in found:
            columns = {row[1] for row in db.execute('PRAGMA table_info("'+name+'")')}
            if not FIELDS <= columns:
                raise ValueError('classic QQ message schema is incomplete')
    return found
