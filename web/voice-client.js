/* SPDX-License-Identifier: AGPL-3.0-or-later */
(async () => {
  if (new URLSearchParams(location.search).get('role') === 'render') return;
  let settings;
  try {
    const response = await fetch('/voice/status');
    if (!response.ok) return;
    settings = await response.json();
  } catch { return; }
  const style = document.createElement('style');
  style.textContent = `#voice-panel{position:fixed;z-index:10000;top:16px;left:16px;width:min(350px,calc(100vw - 48px));padding:14px;background:#082426ed;border:1px solid #5eaaa7;border-radius:12px;color:#d9ffff;font:14px/1.5 system-ui;pointer-events:auto}#voice-panel button,#voice-panel input{font:inherit;border-radius:6px;padding:8px;border:1px solid #528987;background:#103a3c;color:#edffff}#voice-panel button{cursor:pointer}#voice-panel button:disabled{opacity:.5;cursor:wait}#voice-panel form{display:flex;gap:6px;margin-top:8px}#voice-panel input{min-width:0;flex:1}#voice-panel p{margin:8px 0 0}#voice-panel label{display:block;margin-top:8px}#voice-reply{max-height:130px;overflow:auto}#voice-panel[hidden],#voice-toast[hidden]{display:none}#voice-toast{position:fixed;z-index:10000;bottom:24px;left:50%;transform:translateX(-50%);max-width:min(560px,calc(100vw - 48px));padding:8px 14px;background:#082426ed;border:1px solid #5eaaa7;border-radius:999px;color:#d9ffff;font:14px/1.4 system-ui;pointer-events:none}`;
  document.head.append(style);
  const panel = document.createElement('section');
  panel.id = 'voice-panel';
  panel.hidden = true;
  panel.setAttribute('aria-label', 'Cloud voice controls');
  const toast = document.createElement('div');
  toast.id = 'voice-toast';
  toast.hidden = true;
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  document.body.append(toast);
  panel.innerHTML = `<strong>Cloud voice</strong> <span>${settings.agent ? '· Agent' : '· Board commands'}</span>
    <label>Transcription <select id="voice-source" aria-label="Transcription method"><option value="server">Whisper on server</option><option value="browser">Browser speech service</option></select></label>
    <p><button id="voice-record" type="button">Start microphone</button></p>
    <p id="voice-status" role="status" aria-live="polite">Hold Space to talk (up to ${settings.max_seconds}s). Press V to hide this panel.</p>
    <form><input aria-label="Voice command or agent message" placeholder="Or type: disassemble" maxlength="4000" required><button type="submit">Send</button></form>
    <label><input id="voice-speak" type="checkbox" checked> Read replies aloud</label>
    <p id="voice-reply" aria-live="polite"></p>`;
  document.body.append(panel);
  const record = panel.querySelector('#voice-record');
  const status = panel.querySelector('#voice-status');
  const reply = panel.querySelector('#voice-reply');
  const form = panel.querySelector('form');
  const input = form.querySelector('input');
  const send = form.querySelector('button');
  let recorder, recognition, stream, timer, toastTimer, busy = false, starting = false, pttHeld = false, chunks = [];
  const source = panel.querySelector('#voice-source');
  const resetRecord = () => { record.textContent = 'Start microphone'; record.disabled = busy; send.disabled = busy; source.disabled = false; };
  source.addEventListener('change', () => message(source.value === 'browser' ? 'Browser speech may send audio to its provider; only the transcript reaches this server.' : 'Audio is uploaded to this server when you stop recording.'));
  const capturing = () => starting || busy || !!recognition || recorder?.state === 'recording';
  // While the panel is hidden, status messages surface in a small pill that fades after capture ends.
  const hideToastLater = () => {
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { if (capturing()) hideToastLater(); else toast.hidden = true; }, 4000);
  };
  const message = text => {
    status.textContent = text;
    if (!panel.hidden) return;
    toast.textContent = text; toast.hidden = false; hideToastLater();
  };
  const release = () => { clearTimeout(timer); stream?.getTracks().forEach(t => t.stop()); stream = null; };
  async function submit(path, body, type) {
    if (busy) return;
    busy = true; record.disabled = true; send.disabled = true;
    message('Processing on the server…');
    try {
      const response = await fetch(path, {method: 'POST', headers: {'Content-Type': type}, body});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Voice request failed.');
      reply.textContent = data.reply;
      message(`Heard: ${data.transcript}` + (panel.hidden ? ` — ${data.reply}` : ''));
      if (panel.querySelector('#voice-speak').checked && 'speechSynthesis' in window) {
        speechSynthesis.cancel();
        speechSynthesis.speak(new SpeechSynthesisUtterance(data.reply));
      }
    } catch (error) { message(error.message); }
    finally { busy = false; record.disabled = false; send.disabled = false; }
  }
  const stopCapture = () => {
    if (recognition) recognition.stop();
    else if (recorder?.state === 'recording') { recorder.stop(); record.disabled = true; }
  };
  async function startCapture(ptt) {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      message('Microphone access requires HTTPS (or localhost). Use the secure server address.'); return;
    }
    if (source.value === 'browser') {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Recognition) { message('Browser transcription is unavailable. Choose Whisper or type below.'); return; }
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      recognition = new Recognition(); recognition.lang = 'en-US'; recognition.interimResults = false;
      recognition.onresult = event => {
        const text = event.results[0][0].transcript;
        submit('/voice/text', JSON.stringify({text}), 'application/json');
      };
      recognition.onerror = event => message('Browser speech: ' + event.error + '. Try server transcription or type below.');
      recognition.onend = () => { recognition = null; clearTimeout(timer); resetRecord(); };
      try {
        recognition.start(); record.textContent = 'Stop listening'; send.disabled = true; source.disabled = true;
        message(ptt ? 'Listening… release Space to send.' : 'Listening via browser speech service…');
        timer = setTimeout(() => recognition?.stop(), settings.max_seconds * 1000 - 500);
      } catch (error) { recognition = null; resetRecord(); message(error.message); }
      return;
    }
    if (!window.MediaRecorder) { message('Audio recording is unavailable in this browser. You can type below.'); return; }
    starting = true; record.disabled = true;
    try {
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}, video: false});
      const mimeType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'].find(t => MediaRecorder.isTypeSupported(t));
      if (!mimeType) throw new Error('No supported recording format. You can type below.');
      recorder = new MediaRecorder(stream, {mimeType});
      chunks = [];
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      recorder.onerror = () => { release(); message('Microphone recording failed. Try again.'); record.textContent = 'Start microphone'; record.disabled = false; send.disabled = false; };
      recorder.onstop = () => {
        const blob = new Blob(chunks, {type: mimeType});
        release(); source.disabled = false; record.textContent = 'Start microphone';
        if (blob.size) submit('/voice/audio', blob, mimeType);
        else { message('Nothing recorded. Try again.'); record.disabled = false; send.disabled = false; }
      };
      source.disabled = true;
      recorder.start(); record.textContent = 'Stop and send'; record.disabled = false; send.disabled = true;
      message(ptt ? 'Recording… release Space to send.' : 'Recording… Your audio is sent only after you stop.');
      timer = setTimeout(() => { if (recorder?.state === 'recording') recorder.stop(); }, settings.max_seconds * 1000 - 500);
      // Space was released while the microphone was still opening.
      if (ptt && !pttHeld) stopCapture();
    } catch (error) { release(); source.disabled = false; message(error.message); record.disabled = false; send.disabled = false; }
    finally { starting = false; }
  }
  record.addEventListener('click', () => {
    if (busy || starting) return;
    if (recognition || recorder?.state === 'recording') stopCapture();
    else startCapture(false);
  });
  const typing = event => event.target.closest?.('input, textarea, select, button, [contenteditable]');
  addEventListener('keydown', event => {
    if (typing(event) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.code === 'KeyV' && !event.repeat) {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) { toast.hidden = true; clearTimeout(toastTimer); }
      return;
    }
    if (event.code !== 'Space') return;
    event.preventDefault();
    if (event.repeat || pttHeld || capturing()) return;
    pttHeld = true;
    startCapture(true);
  });
  addEventListener('keyup', event => {
    if (event.code !== 'Space' || !pttHeld) return;
    event.preventDefault();
    pttHeld = false;
    stopCapture();
  });
  addEventListener('blur', () => { if (pttHeld) { pttHeld = false; stopCapture(); } });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (busy || starting || recognition || recorder?.state === 'recording' || !input.value.trim()) return;
    submit('/voice/text', JSON.stringify({text: input.value.trim()}), 'application/json');
  });
  window.addEventListener('pagehide', () => { if (recorder) recorder.onstop = null; if (recognition) { recognition.onresult = null; recognition.abort(); } release(); });
})();
