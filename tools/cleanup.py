#!/usr/bin/env python3
"""Preview or delete all resources belonging to one Agent Kernel Lab instance."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from akl.config import Config
from akl.core import LabError, lock
from akl import cleanup


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT/'local/lab.json')
    action = p.add_mutually_exclusive_group()
    action.add_argument('--delete', action='store_true', help='Permanently delete the previewed instance after UUID confirmation')
    action.add_argument('--dry-run', action='store_true', help='Preview only (the default)')
    p.add_argument('--confirm', help='Exact instance UUID for non-interactive deletion')
    p.add_argument('--force', action='store_true', help='With --delete, power off active guests and discard running state')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not args.delete and (args.confirm or args.force):
            raise LabError('--confirm and --force require --delete')
        if os.geteuid() != 0:
            # No passwords are accepted as arguments, read or logged by this program.
            command = ['sudo', sys.executable, str(Path(__file__).resolve()),
                       *(sys.argv[1:] if argv is None else argv)]
            return subprocess.call(command)
        config = Config.load(args.config)
        preview = cleanup.plan(config)
        print(json.dumps({'preview': preview}, indent=2), flush=True)
        if not args.delete:
            print('Preview only. To remove this instance, run cleanup.sh --delete with this same --config.')
            return 0
        confirmation = args.confirm
        if not confirmation:
            if not sys.stdin.isatty():
                raise LabError('Non-interactive deletion requires --confirm INSTANCE_UUID')
            print('This permanently removes the listed VMs, disks, backups, credentials and runtime files.')
            confirmation = input('Type the full instance UUID to delete: ').strip()
        with lock(config):
            result = cleanup.execute(config, confirmation, args.force)
        print(json.dumps({'ok': True, 'result': result}, indent=2))
        return 0
    except (LabError, OSError, ValueError, KeyError, TypeError) as exc:
        print('Cleanup: '+str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nCanceled. If deletion had started, inspect the cleanup journal before retrying.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
