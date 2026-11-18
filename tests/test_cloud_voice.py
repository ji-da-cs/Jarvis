# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/backtalk'))
from cloud_voice import CloudVoice, handler_for, MAX_AUDIO

spec = importlib.util.spec_from_file_location('voice_stage', ROOT / 'vendor/barehands/server.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class CloudVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.voice = CloudVoice(stage, 0)
        (stage.HERE / 'state').mkdir(exist_ok=True)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(stage, cls.voice))
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'
        cls.voice.base = cls.base
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        stage._CMDS.clear()

    def post(self, path, data, content_type='application/json', headers=None):
        req = Request(self.base + path, data=data,
                      headers={'Content-Type': content_type, **(headers or {})})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    @unittest.skipUnless(importlib.util.find_spec('faster_whisper'), 'Install requirements-cloud.txt for the real audio decoder check')
    def test_actual_browser_webm_decodes_without_audio_hardware(self):
        class Recognizer:
            def transcribe(self, pcm, **kwargs):
                if len(pcm) < 1000:
                    raise AssertionError('Recording did not decode into PCM audio')
                return [SimpleNamespace(text='disassemble')], None
        with patch.object(self.voice, 'model', Recognizer()):
            text = self.voice.transcribe((ROOT / 'tests/fixtures/browser-mic.webm').read_bytes())
        self.assertEqual(text, 'disassemble')

    def test_uploaded_audio_reaches_transcriber_and_board(self):
        with patch.object(self.voice, 'transcribe', return_value='show Demo assembly') as transcribe:
            code, result = self.post('/voice/audio', b'recorded-audio', 'audio/webm;codecs=opus')
        self.assertEqual(code, 200)
        transcribe.assert_called_once_with(b'recorded-audio')
        self.assertEqual(result['transcript'], 'show Demo assembly')
        self.assertNotIn('<<', result['reply'])
        self.assertEqual(stage._CMDS[0]['src'], '/media/models/Demo assembly.gltf')
        self.assertEqual((stage.HERE / 'state/state').read_text(), 'idle')

    def test_typed_fallback_and_unknown_model(self):
        code, result = self.post('/voice/text', b'{"text":"disassemble"}')
        self.assertEqual((code, result['commands_queued']), (200, 1))
        stage._CMDS.clear()
        code, _ = self.post('/voice/text', b'{"text":"show absent-model"}')
        self.assertEqual(code, 400)
        self.assertEqual(stage._CMDS, [])

    def test_no_agent_fallback_is_explicit(self):
        code, result = self.post('/voice/text', b'{"text":"Explain the model"}')
        self.assertEqual(code, 503)
        self.assertIn('Agent mode is off', result['error'])

    def test_cross_origin_requests_rejected(self):
        code, _ = self.post('/voice/text', b'{"text":"clear"}',
                            headers={'Origin': 'https://other.example'})
        self.assertEqual(code, 403)
        self.assertEqual(stage._CMDS, [])

    def test_reject_malformed_json_and_unsupported_audio(self):
        for data in (b'[1]', b'null', b'{', b'{"text":22}'):
            code, _ = self.post('/voice/text', data)
            self.assertEqual(code, 400)
        code, _ = self.post('/voice/audio', b'x', 'text/plain')
        self.assertEqual(code, 415)

    def test_busy_requests_are_rejected_without_changing_state(self):
        self.voice.lock.acquire()
        try:
            code, _ = self.post('/voice/text', b'{"text":"assemble"}')
        finally:
            self.voice.lock.release()
        self.assertEqual(code, 409)

    def test_audio_upload_size_limit(self):
        # Advertise a large recording; handler rejects before reading it.
        req = Request(self.base + '/voice/audio', data=b'x',
                      headers={'Content-Type': 'audio/webm',
                               'Content-Length': str(MAX_AUDIO + 1)})
        with self.assertRaises(HTTPError) as caught:
            urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 413)

    def test_bad_agent_actions_do_not_partially_execute(self):
        with patch.object(self.voice, 'answer', return_value='<<board:disassemble>><<board:show missing>>Here.'):
            code, _ = self.post('/voice/text', b'{"text":"request"}')
        self.assertEqual(code, 400)
        self.assertEqual(stage._CMDS, [])


if __name__ == '__main__':
    unittest.main()
