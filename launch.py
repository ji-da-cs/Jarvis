#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Launch the combined motion stage and optional local voice agent."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
BARE = ROOT / 'vendor' / 'barehands'
BACK = ROOT / 'vendor' / 'backtalk'

BOARD_DISCIPLINE = '''You share a live 3D stage controlled by the user's hands.
For requested board actions, put one of these silent tags BEFORE a spoken
sentence: <<board:show Demo assembly>>, <<board:hologram Demo assembly>>,
<<board:explode>>, <<board:assemble>>, <<board:hover>>, <<board:reset>>,
<<board:clear>>. Show accepts a unique model filename/stem from the media folder;
explode/assemble/hover optionally accept a title. Never invent other tags.
Tags execute when their accompanying sentence starts playing. Always include a
spoken sentence after a tag. Board actions only affect this local visual stage.
For available models read vendor/barehands/media/models or GET /props at board_url.
For scene context GET /state at board_url using a read-only tool. Do not claim
that an action succeeded without checking the current scene; a closed stage tab
cannot consume commands. Gestures independently move, rotate, scale and explode
models. Do not edit files to manipulate the scene. Other agent tools retain their
normal permission checks. Do not change permission_mode or access credentials.
'''


def prepare_config(port):
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    # User config is an optional overlay. Never overwrite the user's source file.
    user = ROOT / 'voice.json'
    cfg = json.loads(user.read_text()) if user.exists() else {}
    cfg.update(agent_dir=str(ROOT), barehands_state_dir=str(BARE / 'state'),
               board_url=f'http://127.0.0.1:{port}', signals_dir=str(runtime))
    cfg['discipline_append'] = (cfg.get('discipline_append', '') + '\n' +
                                BOARD_DISCIPLINE).replace('at board_url',
                                f'at http://127.0.0.1:{port}')
    cfg.setdefault('permission_mode', 'ask')
    cfg.setdefault('greeting', 'Motion and voice online. Hold {ptt_key} to talk.')
    path = runtime / 'backtalk.json'
    path.write_text(json.dumps(cfg, indent=2))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice', action='store_true', help='Start Backtalk too')
    parser.add_argument('--port', type=int, default=8794)
    parser.add_argument('--host', default='127.0.0.1', help='Use 0.0.0.0 behind an authenticated HTTPS proxy')
    parser.add_argument('--cloud-voice', action='store_true', help='Receive microphone recordings from the browser')
    parser.add_argument('--cloud-agent', action='store_true', help='Enable Claude conversation for cloud voice')
    parser.add_argument('--stt-model', default='tiny.en', help='Whisper model name or local model directory')
    args = parser.parse_args()
    if args.voice and (args.cloud_voice or args.cloud_agent):
        parser.error('Choose either local --voice or browser --cloud-voice')
    if args.cloud_agent:
        args.cloud_voice = True
    if args.voice:
        if not shutil.which('uv'):
            parser.error('Install uv, then run: uv sync --project vendor/backtalk')
        if not shutil.which('claude'):
            parser.error('Install Claude Code and sign in on this computer first')
        if not (BACK / '.venv').is_dir():
            parser.error('Install voice dependencies: uv sync --project vendor/backtalk')
    spec = importlib.util.spec_from_file_location('barehands_server', BARE / 'server.py')
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    (BARE / 'state').mkdir(exist_ok=True)
    handler = stage.Handler
    if args.cloud_voice:
        sys.path.insert(0, str(BACK))
        from cloud_voice import CloudVoice, handler_for
        cloud = CloudVoice(stage, args.port, model=args.stt_model, agent=args.cloud_agent)
        handler = handler_for(stage, cloud)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    if args.cloud_voice:
        cloud.base = f'http://127.0.0.1:{server.server_port}'
    stage._CMDS.append({'a': 'hand', 'src': '/media/models/Demo assembly.gltf',
                        'title': 'Demo assembly'})
    print(f'Motion stage: http://127.0.0.1:{args.port}/stage.html', flush=True)
    print('Open in Chrome and allow the camera. Ctrl-C stops this launcher.', flush=True)
    voice = None
    try:
        if args.voice:
            cfg = prepare_config(args.port)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            voice = subprocess.Popen(['uv', 'run', '--project', str(BACK),
                                      'python', '-m', 'backtalk.main'], cwd=BACK,
                                     env={**os.environ, 'BACKTALK_CONFIG': str(cfg)})
            result = voice.wait()
            if result:
                print(f'Voice exited with status {result}. See vendor/backtalk/logs.',
                      file=sys.stderr)
            return result
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        if voice is not None and voice.poll() is None:
            voice.terminate()
            try:
                voice.wait(timeout=5)
            except subprocess.TimeoutExpired:
                voice.kill()
                voice.wait()
        if args.voice:
            server.shutdown()
        server.server_close()


if __name__ == '__main__':
    sys.exit(main())
