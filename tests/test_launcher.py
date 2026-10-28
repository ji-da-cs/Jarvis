# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exercise the public launcher, including reuse of its managed Python."""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import unittest
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_default_launch_starts_motion_and_microphone_on_one_server(self):
        python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.exists():
            self.skipTest('Managed cloud dependencies are not installed')
        ready = subprocess.run([str(python), '-c',
                                'import faster_whisper, claude_agent_sdk'], capture_output=True)
        if ready.returncode:
            self.skipTest('Managed cloud dependencies are not installed')
        process = subprocess.Popen([sys.executable, str(ROOT / 'launch.py'), '--port', '0'],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True)
        output = queue.Queue()
        threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True).start()
        try:
            line = output.get(timeout=20)
            match = re.search(r'(http://127.0.0.1:\d+)/stage.html', line)
            self.assertIsNotNone(match, line)
            base = match.group(1)
            with urlopen(base + '/voice/status', timeout=5) as response:
                self.assertTrue(json.load(response)['enabled'])
            with urlopen(base + '/stage.html', timeout=5) as response:
                self.assertIn(b'/voice-client.js', response.read())
            with urlopen(base + '/voice-client.js', timeout=5) as response:
                self.assertIn(b'getUserMedia', response.read())
            req = Request(base + '/voice/text', data=b'{"text":"disassemble"}',
                          headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=5) as response:
                self.assertEqual(json.load(response)['commands_queued'], 1)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()


if __name__ == '__main__':
    unittest.main()
