# SPDX-License-Identifier: AGPL-3.0-or-later
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/backtalk'))
from backtalk.board import command, dispatch, request
import launch

spec = importlib.util.spec_from_file_location('stage', ROOT / 'vendor/barehands/server.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), stage.Handler)
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        stage._CMDS.clear()

    def test_show_real_model_and_consume_once(self):
        dispatch(['board:show Demo assembly'], self.base)
        commands = request(self.base, '/state', {'items': []})
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]['src'], '/media/models/Demo assembly.gltf')
        self.assertEqual(commands[0]['a'], 'hand')
        self.assertEqual(request(self.base, '/state', {'items': []}), [])
        # Fetch and decode the actual self-contained model served to three.js.
        model = request(self.base, '/media/models/Demo%20assembly.gltf')
        self.assertEqual(len(model['nodes']), 6)
        self.assertEqual(model['asset']['version'], '2.0')

    def test_voice_action_order_and_hologram(self):
        dispatch(['board:hologram Demo assembly', 'board:explode',
                  'board:assemble Demo assembly'], self.base)
        commands = request(self.base, '/state', {})
        self.assertEqual([c['a'] for c in commands], ['hand', 'explode', 'assemble'])
        self.assertEqual(commands[0]['mode'], 'holo')
        self.assertEqual(commands[2]['title'], 'Demo assembly')

    def test_no_arbitrary_actions_or_unknown_models(self):
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            dispatch(['unrelated', 'board:shell rm', 'board:show missing'], self.base)
        self.assertIn('Unsupported', errors.getvalue())
        self.assertEqual(request(self.base, '/state', {}), [])

    def test_ambiguous_model_names_rejected(self):
        tree = {'items': ['models/a.glb', 'holo/a.glb']}
        with patch('backtalk.board.request', return_value=tree):
            with self.assertRaises(ValueError):
                command('board:show a', self.base)

    def test_remote_board_endpoint_rejected(self):
        with self.assertRaises(ValueError):
            request('https://example.com', '/props')

    def test_config_preserves_user_preferences_and_wires_both_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = '{"voice":"af_heart", "discipline_append":"Be brief."}'
            (root / 'voice.json').write_text(source)
            with patch.object(launch, 'ROOT', root):
                config = json.loads(launch.prepare_config(9123).read_text())
            self.assertEqual(config['voice'], 'af_heart')
            self.assertEqual(config['permission_mode'], 'ask')
            self.assertEqual(config['board_url'], 'http://127.0.0.1:9123')
            self.assertIn('Be brief.', config['discipline_append'])
            self.assertIn('board:explode', config['discipline_append'])
            self.assertEqual((root / 'voice.json').read_text(), source)


if __name__ == '__main__':
    unittest.main()
