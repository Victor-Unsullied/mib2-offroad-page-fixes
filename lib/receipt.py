"""Private local recovery state for the guided Offroad installer."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


PHASES = frozenset({'prepared', 'apply_pending', 'applied', 'rollback_pending', 'restored'})
SCHEMA = 'offroad-guided-v1'


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


class Receipt:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.path = self.directory / 'offroad.json'

    @contextmanager
    def lock(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.directory / 'offroad.lock').open('a+b') as lock:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError('Another installer holds this state folder, or it cannot be locked') from error
            # Closing the handle releases the operating-system lock, including after a crash.
            yield

    def load(self, host, identity_digest):
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            envelope = json.loads(raw)
            value = envelope['receipt']
            valid = (
                set(value) == {'schema', 'host', 'identity_sha256', 'original_enabled', 'phase'}
                and envelope['sha256'] == hashlib.sha256(encode(value)).hexdigest()
                and value['schema'] == SCHEMA
                and type(value['original_enabled']) is bool
                and value['phase'] in PHASES
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError('Recovery receipt is unreadable. Preserve the state folder.') from error
        if not valid:
            raise ValueError('Recovery receipt failed verification. Preserve the state folder.')
        if value['host'] != str(host) or value['identity_sha256'] != identity_digest:
            raise ValueError('Recovery receipt belongs to a different address or head-unit identifier')
        return value

    def save(self, value):
        payload = {'receipt': value, 'sha256': hashlib.sha256(encode(value)).hexdigest()}
        temporary = None
        try:
            with NamedTemporaryFile(dir=self.directory, prefix='.offroad-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encode(payload) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != 'nt':
                descriptor = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
