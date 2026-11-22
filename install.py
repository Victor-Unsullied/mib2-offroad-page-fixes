"""Prepare and run the temperature-only Offroad repair."""

import argparse
from hashlib import sha256
from http.client import HTTPException
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'state' / 'temperature'
SPORT_COMMIT = '100c8b3617203f5706d968700329854160eaab9d'
SPORT_ARCHIVE = (
    'https://codeload.github.com/Victor-Unsullied/mib2-sports-gauges/zip/' + SPORT_COMMIT
)
SPORT_SHA256 = '8cf350a21adae8cf2d7ef05bb27939af6a121a68dee57796b1a6731ca2aa3132'
MAX_ARCHIVE_BYTES = 1024 * 1024


def verify_archive(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES or sha256(data).hexdigest() != SPORT_SHA256:
        raise ValueError(f'Sport Gauges download failed verification. Check or remove the archive at {path}.')
    return data


def prepare_archive(state):
    cache = state / 'sports.zip'
    if cache.exists():
        return verify_archive(cache)

    print('Downloading the verified Sport Gauges repair from GitHub. No connection to the car is needed yet.', flush=True)
    with TemporaryDirectory(dir=state) as temporary:
        incoming = Path(temporary) / 'sports.zip'
        with urlopen(SPORT_ARCHIVE, timeout=25) as response:
            incoming.write_bytes(response.read(MAX_ARCHIVE_BYTES + 1))
        data = verify_archive(incoming)
        os.replace(incoming, cache)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check', action='store_const', dest='action', const='--check',
                         help='verify the downloaded repair and profile without connecting to the car')
    actions.add_argument('--plan', action='store_const', dest='action', const='--plan',
                         help='show the temperature repair steps without connecting to the car')
    actions.add_argument('--inspect', action='store_const', dest='action', const='--inspect',
                         help='check the connected head unit without changing it')
    actions.add_argument('--rollback', action='store_const', dest='action', const='--rollback',
                         help='restore the backup made before this temperature repair')
    args = parser.parse_args(argv)

    if sys.version_info < (3, 10):
        parser.error('Use Python 3.10 or later.')
    if args.action not in ('--check', '--plan') and sys.platform != 'win32':
        parser.error('Use Windows for head-unit operations. --check and --plan also work on this computer.')
    if args.action == '--rollback':
        records = ('session.json', 'session.recovery', 'native/owner.json',
                   'native/transaction.json', 'native/recovery.json')
        if not any((STATE / name).is_file() for name in records):
            parser.error('No temperature repair records were found. Run rollback from the original installer folder.')

    try:
        STATE.mkdir(parents=True, exist_ok=True)
        archive = prepare_archive(STATE)
        with TemporaryDirectory(prefix='mib2-offroad-') as temporary:
            # Extract only the bytes that passed verification.
            with ZipFile(BytesIO(archive)) as bundle:
                bundle.extractall(temporary)
            engine = Path(temporary) / f'mib2-sports-gauges-{SPORT_COMMIT}'
            command = [sys.executable, '-I', '-B', str(ROOT / 'lib' / 'temperature_engine.py'),
                       str(engine), str(STATE), str(ROOT / 'docs' / 'offroad-temperature.xml')]
            if args.action:
                command.append(args.action)
            return subprocess.run(command, cwd=engine).returncode
    except (OSError, HTTPException, ValueError, BadZipFile, KeyboardInterrupt) as error:
        print(f'Offroad installer stopped. {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
