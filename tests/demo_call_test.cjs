const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
const demo = html.slice(html.indexOf('async function demoCall()'), html.indexOf('\nfunction finishDemo'));

async function runCall(greetingOnSilence, delayedCallerReply = false) {
  const elements = new Map();
  const timers = new Set();
  const observations = { callerFrames: 0, prematureCallerFrames: 0, silentFrames: 0, finished: false };
  let greeted = false;
  const wav = new ArrayBuffer(44 + 960);
  new Int16Array(wav, 44).fill(100);
  class Socket {
    static OPEN = 1;
    constructor() {
      this.readyState = 1;
      queueMicrotask(() => this.onopen());
    }
    send(raw) {
      const e = JSON.parse(raw);
      if (e.type === 'session.update') {
        queueMicrotask(() => this.onmessage({ data: JSON.stringify({ type: 'session.ready' }) }));
      } else if (e.type === 'input.audio') {
        const bytes = Buffer.from(e.audio, 'base64');
        if (bytes.some(v => v !== 0)) {
          observations.callerFrames++;
          if (!greeted) observations.prematureCallerFrames++;
          const reply = () => this.onmessage({ data: JSON.stringify({ type: 'transcript.agent', text: 'Thank you.' }) });
          if (delayedCallerReply) setTimeout(reply, 80); else queueMicrotask(reply);
        } else {
          observations.silentFrames++;
          if (greetingOnSilence && !greeted) {
            greeted = true;
            queueMicrotask(() => this.onmessage({ data: JSON.stringify({ type: 'transcript.agent', text: 'Hello.' }) }));
          }
        }
      }
    }
  }
  class AudioContext {
    resume() { return Promise.resolve(); }
    createMediaStreamDestination() { observations.initialPlaybackAt = context.playAt; return { stream: {} }; }
    createBuffer(_, length) { return { getChannelData: () => new Float32Array(length) }; }
    createBufferSource() { return { connect() {}, start() {} }; }
  }
  const context = {
    config: {}, ws: null, audioCtx: null, mix: null, recorder: null, recorded: [], pending: [], lastEvent: null, playAt: 600,
    demoSilenceTimer: null, sendingCallerAudio: false,
    AudioContext, MediaRecorder: class { start() {} }, WebSocket: Socket,
    Int16Array, Uint8Array, performance, Promise,
    btoa: s => Buffer.from(s, 'binary').toString('base64'),
    fetch: async url => ({ ok: true, json: async () => url.includes('script') ? [{ file: 'caller.wav', text: 'Test caller.' }] : { token: 'test' }, arrayBuffer: async () => wav }),
    $: id => { if (!elements.has(id)) elements.set(id, {}); return elements.get(id); },
    out: () => [], line() {}, play() {}, runTool() {}, flush() {},
    setTimeout: (fn, ms) => setTimeout(fn, delayedCallerReply && ms >= 1000 ? ms / 1000 : Math.min(ms, 15)), clearTimeout,
    setInterval: fn => { const id = setInterval(fn, 2); timers.add(id); return id; }, clearInterval,
    finishDemo: message => { observations.finished = true; observations.message = message; clearInterval(context.demoSilenceTimer); },
  };
  vm.createContext(context);
  vm.runInContext(demo, context);
  try { await context.demoCall(); await new Promise(r => setTimeout(r, 25)); }
  finally { for (const id of timers) clearInterval(id); }
  return observations;
}

test('a missing greeting aborts without playing caller speech', async () => {
  const result = await runCall(false);
  assert.equal(result.callerFrames, 0, 'caller speech must not start after a greeting timeout');
});

test('audio keeps flowing during the greeting and caller waits for it', async () => {
  const result = await runCall(true);
  assert.ok(result.silentFrames > 0, 'send silence while the agent is speaking');
  assert.equal(result.prematureCallerFrames, 0, 'wait for the greeting before caller speech');
  assert.equal(result.callerFrames, 1);
  assert.ok(result.finished);
});

test('a new call resets the previous audio playback clock', async () => {
  const result = await runCall(true);
  assert.equal(result.initialPlaybackAt, 0, 'a new AudioContext must not inherit the old playback queue');
});

test('a slow spoken reply can finish without a premature 45 second timeout', async () => {
  const result = await runCall(true, true);
  assert.equal(result.message, undefined, 'allow the observed long voice response to complete');
});
