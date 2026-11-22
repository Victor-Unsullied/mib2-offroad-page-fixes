"""Standalone Offroad configuration and recovery for the reviewed Delphi MIB2."""
import argparse
from ipaddress import IPv4Address
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'lib'))
import package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choices = parser.add_mutually_exclusive_group()
    choices.add_argument('--check', action='store_const', dest='guided', const='verify',
                         help='verify the package offline')
    choices.add_argument('--plan', action='store_const', dest='guided', const='plan',
                         help='read the installation plan offline')
    choices.add_argument('--inspect', action='store_const', dest='guided', const='inspect',
                         help='run guided read-only inspection')
    choices.add_argument('--rollback', action='store_const', dest='guided', const='rollback',
                         help='restore the original state recorded by the guided installer')
    parser.add_argument('action', nargs='?', choices=['verify', 'plan', 'inspect', 'apply', 'rollback'],
                        help='legacy CLI command')
    parser.add_argument('--live', action='store_true', help='allow a legacy command to connect')
    parser.add_argument('--host', type=IPv4Address, help='IPv4 address of your head unit')
    parser.add_argument('--state-dir', type=Path, help='private state folder for the guided installer')
    parser.add_argument('--language', '--lang', dest='lang', choices=['en', 'tr'],
                        help='select the guided installer language')
    args = parser.parse_args(argv)

    if args.action and (args.guided or args.state_dir or args.lang):
        parser.error('Choose either a guided option or a legacy command')
    if args.live and not args.action:
        parser.error('--live is for legacy commands')

    action = args.action or args.guided or 'apply'
    if action == 'plan':
        print((ROOT / 'RUNBOOK.txt').read_text(encoding='utf-8'))
        return 0

    package.integrity()
    if action == 'verify':
        package.invoke('native_menu.py', ['verify'])
        print('Package check complete. Use --plan to review the steps.')
        return 0

    if args.action:
        if not args.live:
            parser.error('--live required for device actions')
        if args.host is None:
            parser.error('--host required for device actions')
        package.invoke('native_menu.py', [action, '--live', '--host', str(args.host)])
        return 0

    import guided

    guided.run(action, args.host, (args.state_dir or ROOT / 'state').resolve(), args.lang)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print('Cancelled / İptal edildi.', file=sys.stderr)
        sys.exit(2)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
