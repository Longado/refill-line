// Mic capture: resample the context's native rate to 24 kHz PCM16 (works on Chrome, Firefox and Safari).
class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.ratio = options.processorOptions.inputSampleRate / 24000;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    const n = Math.floor(input.length / this.ratio);
    const pcm16 = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const s = input[Math.floor(i * this.ratio)] ?? 0;
      pcm16[i] = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
    }
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    return true;
  }
}
registerProcessor("pcm-processor", PCMProcessor);
