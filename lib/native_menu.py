"""Apply only this package native menu bit; preserve other installed features."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from ipaddress import IPv4Address
import json
from pathlib import Path
import socket
import struct

import read_baseline as baseline

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
CONFIG = json.loads((PACKAGE/'MENU.json').read_text())
OWN_KEY = CONFIG['key']
OWN_OFFSET = CONFIG['offset']
NS = 27263191
FEATURES = ((OWN_KEY, OWN_OFFSET, CONFIG['name']),)
READS = baseline.reads.READS
BASELINE_DIGESTS = CONFIG['baseline_sha256']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def invoke_int(key, value=None):
    require(type(key) is int and key == OWN_KEY, 'Only this package native menu key is allowed')
    require(value is None or type(value) is int and value in (0, 1),
            'Expected Offroad scalar 0 or 1')
    method = 'readInt' if value is None else 'writeInt'
    arguments = b'\0' + struct.pack('>i', NS) + b'\1' + struct.pack('>q', key)
    if value is not None:
        arguments += b'\0' + struct.pack('>i', value)
    return baseline.reads.envelope(102, b'\0' + baseline.reads.string(baseline.reads.SERVICE)
        + struct.pack('>i', 0) + baseline.reads.string(method)
        + struct.pack('>i', 2 if value is None else 3) + arguments)


def verify():
    # Compare request encodings against offline reference requests.
    observed = set()
    for row in (PACKAGE / 'data/fixtures/codec.log').read_text().splitlines():
        if not row.startswith('PAYLOAD '):
            continue
        _, method, value, encoded = row.split()
        request = invoke_int(OWN_KEY, None if method == 'readInt' else int(value))
        require(request[31:] == bytes.fromhex(encoded), 'Offroad request encoding mismatch')
        observed.add((method, value))
    require(observed == {('readInt', '0'), ('writeInt', '0'), ('writeInt', '1')},
            'Incomplete request fixtures')
    require(set(BASELINE_DIGESTS) == {name for name, _, _, _ in READS},
            'Incomplete baseline digests')
    print('Offroad configuration checks passed.')


def read_blocks(session):
    return {name: session.read_buffer(ns, key) for name, ns, key, _ in READS}


def validate(blocks):
    actual = bytearray(blocks['CarFuncAdap'])
    require(len(actual) == 60, 'Unexpected native menu group length')
    for offset in (OWN_OFFSET, CONFIG['preserved_other_menu_offset']):
        actual[offset] &= 254
    normalized = dict(blocks, CarFuncAdap=bytes(actual))
    for name, _, _, length in READS:
        data = normalized[name]
        require(len(data) == length and hashlib.sha256(data).hexdigest() == BASELINE_DIGESTS[name],
                'Unreviewed baseline: ' + name)
    require(bool(blocks['Coding'][24] & 4), 'Navigation coding prerequisite missing')


def read_verified(session):
    before = read_blocks(session)
    validate(before)
    scalars = {key: session.read_int(key) for key, _, _ in FEATURES}
    for key, offset, _ in FEATURES:
        require(scalars[key] == (before['CarFuncAdap'][offset] & 31),
                'Native scalar/group mismatch')
    return before, scalars


def change(session, enable, save, *, expected_enabled=None):
    """Perform at most one scalar write for each bit, with fresh exact readbacks."""
    require(type(enable) is bool, 'Expected boolean target state')
    before, scalars = read_verified(session)
    if expected_enabled is not None:
        require(bool(scalars[OWN_KEY] & 1) == expected_enabled,
                'Offroad state changed after the initial read')
    report = {'state': 'BASELINE_VERIFIED', 'device_writes': 0,
              'before': {name: data.hex() for name, data in before.items()},
              'before_scalars': scalars, 'changes': [], 'target_enabled': enable}
    save(report)
    current = dict(before)
    for key, offset, feature in FEATURES:
        value = scalars[key]
        desired = value | 1 if enable else value & 30
        if desired == value:
            report['changes'].append({'feature': feature, 'state': 'ALREADY_EXPECTED'})
            save(report)
            continue
        # Recheck every buffer immediately before each possible mutation.
        fresh = read_blocks(session)
        require(fresh == current and session.read_int(key) == value,
                'Native state changed before write')
        candidate = bytearray(current['CarFuncAdap'])
        candidate[offset] = candidate[offset] | 1 if enable else candidate[offset] & 254
        candidate = bytes(candidate)
        report.update(state='ONE_SCALAR_WRITE_ATTEMPTING', pending_key=key)
        report['device_writes'] += 1
        save(report)
        wire = invoke_int(key, desired)
        session.sent.append({'label': 'ONE native menu writeInt ' + str(key), 'hex': wire.hex()})
        session.sock.sendall(wire)
        success = False
        for _ in range(3):
            scalar = session.read_int(key)
            actual = session.read_buffer(28442848, 101)
            if scalar == desired and actual == candidate:
                success = True
                break
            require(scalar in (value, desired) and actual in (current['CarFuncAdap'], candidate),
                    'Unexpected state after native write; inspect saved evidence')
        require(success, 'Native write not verified; no automatic write retry')
        current['CarFuncAdap'] = candidate
        require(read_blocks(session) == current, 'Unrelated native configuration changed')
        report['changes'].append({'feature': feature, 'key': key, 'byte': offset,
                                  'before': value, 'after': desired, 'state': 'VERIFIED'})
        report.update(state='SCALAR_AND_FULL_GROUP_VERIFIED', pending_key=None)
        save(report)
    report.update(state='PASS_NATIVE_'+CONFIG['name'].upper()+('_ENABLED' if enable else '_DISABLED'),
                  after={name: data.hex() for name, data in current.items()},
                  after_sha256=hashlib.sha256(current['CarFuncAdap']).hexdigest())
    save(report)
    return report


@contextmanager
def open_session(host, source=None):
    source_address = (str(source), 0) if source is not None else None
    with socket.create_connection((str(host), 15001), timeout=3, source_address=source_address) as sock:
        sock.settimeout(.2)
        session = baseline.Session(sock)
        sock.sendall(baseline.reads.registration_request())
        yield session


def run(action, host):
    verify()
    output = HERE / 'live' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    session = None
    report = {'action': action, 'device_writes': 0}
    def save(details):
        report.update(details)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        with open_session(host) as session:
            if action == 'inspect':
                blocks = read_blocks(session)
                save({'buffers': {name: data.hex() for name, data in blocks.items()},
                      'scalars': {str(key): session.read_int(key) for key, _, _ in FEATURES},
                      'state': 'READ_ONLY_COMPLETE'})
            else:
                change(session, action == 'apply', save)
    except Exception as error:
        save({'error': repr(error)})
        raise
    finally:
        if session is not None:
            (output / 'capture.bin').write_bytes(session.raw)
            save({'events': session.events, 'requests': session.sent})
        print(json.dumps({'output': str(output), 'state': report.get('state'),
                          'device_writes': report['device_writes']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['verify', 'inspect', 'apply', 'rollback'])
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--host', type=IPv4Address, help='IPv4 address of your head unit')
    args = parser.parse_args()
    if args.action == 'verify':
        verify()
    elif args.live and args.host is not None:
        run(args.action, args.host)
    else:
        parser.error('--live and --host required for device actions')
