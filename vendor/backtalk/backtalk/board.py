# SPDX-License-Identifier: AGPL-3.0-or-later
"""Narrow, local-only adapter from spoken stage directions to the 3D board.

Only board: tags opt in. No shell, file writes, or arbitrary URLs are exposed.
Failures are reported to stderr without interrupting speech playback.
"""
import json
import sys
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def request(base, path, payload=None):
    url = urlsplit(base)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') \
            or url.username or url.password or url.path not in ('', '/') \
            or url.query or url.fragment:
        raise ValueError('Board URL must be a loopback HTTP origin')
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base.rstrip('/') + path, data=data,
                  headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=1) as response:
        body = response.read()
        return json.loads(body) if body else None


def model_paths(tree):
    for item in tree.get('items', []):
        if PurePosixPath(item).suffix.lower() in ('.glb', '.gltf'):
            yield item
    for child in tree.get('dirs', []):
        yield from model_paths(child)


def command(direction, base):
    """Return None for unrelated tags; reject invalid or ambiguous actions."""
    if not direction.startswith('board:'):
        return None
    verb, _, target = direction[6:].strip().partition(' ')
    target = target.strip()
    if verb in ('show', 'hologram'):
        if not target:
            raise ValueError('Name a model to show')
        paths = list(model_paths(request(base, '/props')))
        exact = [p for p in paths if target.casefold() in
                 (p.casefold(), PurePosixPath(p).stem.casefold())]
        matches = exact or [p for p in paths if target.casefold() in p.casefold()]
        if len(matches) != 1:
            raise ValueError(f'Model name must match exactly one file: {target}')
        return {'a': 'hand', 'src': '/media/' + matches[0],
                'title': PurePosixPath(matches[0]).stem,
                'mode': 'holo' if verb == 'hologram' else 'solid'}
    if verb in ('explode', 'assemble', 'hover'):
        return {'a': verb, **({'title': target} if target else {})}
    if verb in ('reset', 'clear') and not target:
        return {'a': verb}
    raise ValueError(f'Unsupported board direction: {verb}')


def dispatch(directions, base):
    if not base:
        return
    for direction in directions:
        try:
            cmd = command(direction, base)
            if cmd:
                request(base, '/cmd', cmd)
        except Exception as error:
            print(f'[board] {error}', file=sys.stderr, flush=True)
