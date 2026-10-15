#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Send the same bounded commands used by voice, or inspect the scene."""
import argparse
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vendor' / 'backtalk'))
from backtalk.board import command, request

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', help='state, models, or e.g. "show Demo assembly"')
    parser.add_argument('--port', type=int, default=8794)
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    try:
        if args.action in ('state', 'models'):
            print(json.dumps(request(base, '/state' if args.action == 'state' else '/props'), indent=2))
        else:
            request(base, '/cmd', command('board:' + args.action, base))
            print('Queued. The open stage consumes this on its next heartbeat.')
    except Exception as error:
        parser.exit(1, f'{error}\n')
