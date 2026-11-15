#!/usr/bin/env python3
"""Owner tool on the Mac: pair, list or revoke remote FlixTor TVs.

  pair_device.py --label "Living room TV" --profile <profile name or id> [--replace]
  pair_device.py --list
  pair_device.py --revoke "Living room TV"

Pairing prints a one-time code (8 characters, valid 15 minutes). Type it on the TV under
Recommendations profile -> Connect to recommendations. Only hashes are stored.
"""
import argparse, sys
from pathlib import Path
from devices import DeviceRegistry, DeviceError, CODE_TTL
from profiles import RecommendationProfiles

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO.parent/'private-imports/amazon/personalized'
DEFAULT_DEVICES = REPO.parent/'private-imports/remote/devices.json'


def resolve(entries, wanted):
    """Profile name or id -> id. Names match case-insensitively and must be unique."""
    exact = [e for e in entries if e['id'] == wanted]
    named = [e for e in entries if e['name'].lower() == wanted.lower()]
    found = exact or named
    if len(found) != 1:
        raise DeviceError('Unknown or ambiguous profile "%s". Known: %s' % (wanted, ', '.join(e['name'] for e in entries)))
    return found[0]['id']


def main(argv=None, out=sys.stdout):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--devices', default=str(DEFAULT_DEVICES))
    p.add_argument('--data', default=str(DEFAULT_DATA), help='Recommendation data dir (to resolve profiles)')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--label')
    g.add_argument('--list', action='store_true')
    g.add_argument('--revoke', metavar='LABEL')
    p.add_argument('--profile', action='append', help='Profile name or id (repeat for more)')
    p.add_argument('--replace', action='store_true', help='Re-pair an existing label; its old token stops working')
    a = p.parse_args(argv)
    registry = DeviceRegistry(a.devices)
    entries = RecommendationProfiles(a.data).entries()
    names = {e['id']: e['name'] for e in entries}
    try:
        if a.list:
            rows = registry.summary()
            for d in rows:
                print('%-24s %-13s %s' % (d['label'], d['status'], ', '.join(names.get(i, i+' (missing)') for i in d['profiles'])), file=out)
            if not rows:
                print('No paired devices.', file=out)
        elif a.revoke:
            registry.revoke(a.revoke)
            print('Revoked %s. Its TV will show "Connection removed".' % a.revoke, file=out)
        else:
            if not a.profile:
                p.error('--label needs --profile')
            ids = [resolve(entries, w) for w in a.profile]
            code = registry.create(a.label, ids, replace=a.replace)
            print('Pairing code for %s (%s): %s-%s' % (a.label, ', '.join(names[i] for i in ids), code[:4], code[4:]), file=out)
            print('Single use, valid %d minutes. Enter it on the TV: Recommendations profile -> Connect to recommendations.' % (CODE_TTL//60), file=out)
    except DeviceError as error:
        print('Error: %s' % error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
