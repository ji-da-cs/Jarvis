# Motion Voice Studio

A combined [Barehands](https://github.com/jaredrhod/barehands) +
[Backtalk](https://github.com/jaredrhod/backtalk) workspace: manipulate 3D models
with your hands while talking to a Claude Code agent that shares the same stage.

## Start the motion stage

Requires Python 3.11 or 3.12 and Chrome on a computer with a webcam.

```sh
python3 launch.py
```

Open the address printed by the launcher in Chrome and allow camera access.
A six-piece demo assembly is queued automatically. For model/voice work without
a webcam, append `?camera=0` to the printed stage address; gesture tracking is
disabled in that mode. Pinch-drag to move it, hold
still while carrying it to rotate, use two hands to scale, flick to throw, or
pinch empty space and drag sideways to scrub its exploded view. Tap the ring to
browse Notes and Props. See the upstream gesture guide in
`vendor/barehands/sample-notes/Getting Started/The Gestures.md`.

Drop your own `.glb` files or self-contained `.gltf` files into
`vendor/barehands/media/models/`. glTF files with external buffers/textures must
keep their companion files at the paths referenced by the model.

## Add the voice agent

Run this on your **local computer**: Backtalk opens the microphone, speakers,
and a global push-to-talk key on the machine running Python. A cloud server
cannot listen to your laptop's microphone through this native integration.

Prerequisites:

- Python 3.11–3.12 and [uv](https://docs.astral.sh/uv/).
- [Claude Code](https://code.claude.com/docs/en/setup), installed and signed in
  using your own account. Agent turns use that account's usage.
- espeak-ng and PortAudio. On Debian/Ubuntu:
  `sudo apt-get install espeak-ng libportaudio2 portaudio19-dev`.
  On macOS: `brew install espeak-ng portaudio`.
- Camera and Microphone access; macOS also requires Input Monitoring for the
  terminal app. Linux needs a desktop session for the global keyboard hook.

```sh
uv sync --project vendor/backtalk
# Optional: copy voice.json.example to voice.json and choose a voice/key/model.
python3 launch.py --voice
```

First voice use downloads Whisper and Kokoro speech models (roughly 1 GB,
plus Python dependencies). The default PyTorch install can be several GB on
Linux with CUDA packages. For CPU-only machines, consult PyTorch's official
CPU wheel installation instructions before syncing. No speech API key is
required for the built-in voice. Model downloads need Hugging Face access;
hand tracking and rendering need the CDNs referenced in `stage.html`.

Hold **Home**, speak, and release. Try:

- “Show the Demo assembly as a hologram.”
- “Explode the model. Explain how the pieces fit.”
- “Put it back together.”
- “Highlight that model.”
- “Reset the stage.”

The spoken reply carries silent `board:` directions. They execute at the start
of the corresponding audio chunk through a local command bridge, while your
hands continue controlling the model. The ring mirrors listening, thinking and
speaking, including the voice waveform. Commands are queued until an open stage
page sends its heartbeat; a queued command is not proof it rendered.

The launcher generates `.runtime/backtalk.json`, wiring the agent's working
folder, board URL, shared state, and board vocabulary. `voice.json` is an optional
user overlay, never overwritten. Push-to-talk and Backtalk's existing permission
prompts remain the defaults. The stage bridge only accepts show, hologram,
explode, assemble, hover, reset and clear; it cannot execute shell commands.
The Claude agent retains Backtalk's normal tools and permission checks.

Ctrl-C stops the processes started by this launcher. `--port 9000` selects a
different local port for both components. Existing servers or voice sessions
are never killed to make room for a new instance.

## Inspect or control without voice

With the launcher running:

```sh
python3 tools/board.py models
python3 tools/board.py 'show Demo assembly'
python3 tools/board.py explode
python3 tools/board.py assemble
python3 tools/board.py state
python3 -m unittest discover -s tests -v
```

The tests start a real ephemeral Barehands HTTP server, load the demo model,
exercise commands through the stage heartbeat, verify ordering and consumption,
and reject unsupported actions and ambiguous models. They do not simulate a
human hand or authenticate Claude. An optional browser check requires
Playwright and an installed Chromium; with the launcher running, execute
`python3 tools/browser_smoke.py --browser /path/to/chromium`. It checks the live
camera-off stage and saves `.runtime/browser-smoke.png` for visual inspection.

## Architecture and source

```text
Webcam → MediaPipe → Barehands / three.js → 3D scene
                         ↑ /cmd       ↓ /state
Microphone → Whisper → Claude agent → silent board directions
                           ↓                 ↓
                      Kokoro voice    bounded local bridge
                           ↓
                    shared ring state / waveform
```

Both upstream projects are included under `vendor/` so this repository is
self-contained. Their original docs and licenses are retained. This integration
adds a launcher, a narrow adapter in `backtalk/board.py`, a call from
`backtalk/signals.py`, camera-off startup and branding in `stage.html`, and an
original procedural demo model. Upstream snapshots:

- Barehands: `eb23bed2d772f9d5a24de26fb92f46c3c76d69cf`
- Backtalk: `84b3a6cd321060cabb74aad6ebe794621cf99bd3`

Copyright © 2026 Jared Rhodenizer for the upstream projects. Distributed under
**AGPL-3.0-or-later**; see [LICENSE](LICENSE). Keep the source and attribution
available when distributing or hosting modified versions.
