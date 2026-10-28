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


MODEL_SUFFIXES = ('.glb', '.gltf')
# Spoken verb -> stage action. "disassemble" drives the stage's explode view.
VERBS = {'disassemble': 'explode', 'assemble': 'assemble', 'hover': 'hover'}


def media_paths(tree):
    """Every stageable file in the media airlock: models/, fx/, holo/, misc/."""
    yield from tree.get('items', [])
    for child in tree.get('dirs', []):
        yield from media_paths(child)


def find_media(target, base):
    paths = list(media_paths(request(base, '/props')))
    key = target.casefold()
    # Exact match on path, path without extension, or file stem; else substring.
    exact = [p for p in paths if key in (p.casefold(), str(PurePosixPath(p).with_suffix('')).casefold(),
                                         PurePosixPath(p).stem.casefold())]
    matches = exact or [p for p in paths if key in p.casefold()]
    if len(matches) != 1:
        raise ValueError(f'Name must match exactly one media file: {target}')
    return matches[0]


def command(direction, base):
    """Return None for unrelated tags; reject invalid or ambiguous actions."""
    if not direction.startswith('board:'):
        return None
    verb, _, target = direction[6:].strip().partition(' ')
    target = target.strip()
    if verb in ('show', 'hologram'):
        if not target:
            raise ValueError('Name a model or prop to show')
        path = find_media(target, base)
        cmd = {'a': 'hand', 'src': '/media/' + path, 'title': PurePosixPath(path).stem}
        if verb == 'hologram':
            if PurePosixPath(path).suffix.lower() not in MODEL_SUFFIXES:
                raise ValueError(f'Hologram needs a 3D model, not an image: {target}')
            cmd['mode'] = 'holo'
        # "show" leaves mode unset so the folder decides: holo/ renders as the
        # blue wire, fx/ renders frameless, models/ and misc/ render normally.
        return cmd
    if verb in VERBS:
        return {'a': VERBS[verb], **({'title': target} if target else {})}
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
