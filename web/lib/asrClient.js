// ASR client — getUserMedia + AudioWorklet → 16k Int16 PCM frames → BFF WebSocket
//
// Usage:
//   const asr = new ASRClient({
//     wsUrl:    'ws://127.0.0.1:8891/api/v1/asr/ws',  // bridge endpoint
//     config:   { wsUrl, apiAppId, apiAccessKey, ... },  // 火山引擎 init payload
//     onPartial(text)  { ... },
//     onFinal(text)    { ... },
//     onError(err)     { ... },
//     onState(state)   { ... },  // 'idle' | 'connecting' | 'recording' | 'closed' | 'error'
//   });
//   await asr.start();
//   ...
//   await asr.stop();

const STATES = ['idle', 'requesting-mic', 'connecting', 'recording', 'closing', 'closed', 'error'];

export class ASRClient {
  constructor({ wsUrl, config, onPartial, onFinal, onError, onState }) {
    this.bridgeUrl = wsUrl;
    this.config = config;
    this.onPartial = onPartial || (() => {});
    this.onFinal = onFinal || (() => {});
    this.onError = onError || (() => {});
    this.onState = onState || (() => {});
    this.ws = null;
    this.stream = null;
    this.audioCtx = null;
    this.workletNode = null;
    this.source = null;
    this.state = 'idle';
    this.transcript = '';     // 累积后的"完整文本"
    this._committed = '';     // 已经定型的部分
    this._lastPartial = '';   // 上一次收到的 partial（in-progress）
  }

  _setState(s) {
    this.state = s;
    try { this.onState(s); } catch (_) {}
  }

  async start() {
    if (this.state !== 'idle' && this.state !== 'closed' && this.state !== 'error') {
      throw new Error(`ASRClient: cannot start in state ${this.state}`);
    }
    this.transcript = '';
    this._committed = '';
    this._lastPartial = '';

    // 1. mic
    this._setState('requesting-mic');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch (e) {
      this._setState('error');
      throw new Error('麦克风授权失败：' + e.message);
    }

    // 2. ws bridge
    this._setState('connecting');
    try {
      await this._connectWs();
    } catch (e) {
      this._cleanupStream();
      this._setState('error');
      throw e;
    }

    // 3. audio worklet
    try {
      this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      await this.audioCtx.audioWorklet.addModule('/lib/pcm-worklet.js');
      this.source = this.audioCtx.createMediaStreamSource(this.stream);
      this.workletNode = new AudioWorkletNode(this.audioCtx, 'pcm16-worklet', {
        processorOptions: { batchMs: 100 },
      });
      this.workletNode.port.onmessage = (e) => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(e.data);
        }
      };
      this.source.connect(this.workletNode);
      // do not connect to destination — we don't want to play it back
      this._setState('recording');
    } catch (e) {
      this._cleanupAll();
      this._setState('error');
      throw new Error('AudioWorklet 启动失败：' + e.message);
    }
  }

  async stop() {
    if (this.state === 'idle' || this.state === 'closed') return;
    this._setState('closing');
    // tell upstream this is the end
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('__END__');
      }
    } catch (_) {}
    // give upstream a moment to flush
    await new Promise(r => setTimeout(r, 600));
    this._cleanupAll();
    this._setState('closed');
    return this.transcript;
  }

  _connectWs() {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(this.bridgeUrl);
      this.ws = ws;
      let opened = false;
      const fail = (msg) => { if (!opened) reject(new Error(msg)); };

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'init', config: this.config }));
      };
      ws.onerror = (e) => fail('WebSocket error');
      ws.onclose = (e) => {
        if (!opened) fail(`WebSocket closed before bridge open (code=${e.code})`);
        else if (this.state === 'recording') {
          this.onError(new Error(`upstream closed (code=${e.code})`));
          this._setState('error');
        }
      };
      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch (_) { return; }
        if (msg.type === 'bridge_open') {
          opened = true;
          resolve();
        } else if (msg.type === 'partial' && msg.text) {
          this._handleIncomingText(msg.text, false);
        } else if (msg.type === 'final' && msg.text) {
          this._handleIncomingText(msg.text, true);
        } else if (msg.type === 'error' || msg.type === 'upstream_error' || msg.type === 'bridge_error') {
          fail(msg.message || 'bridge error');
          if (opened) {
            this.onError(new Error(msg.message || 'bridge error'));
            this._setState('error');
          }
        }
      };
    });
  }

  /**
   * 智能累积：处理服务端可能返回的两种语义
   *  - full: 每次都是完整累积文本 → 直接采用
   *  - single: 每次只是当前句，新句进来时把上一句 commit 掉
   *
   * 判断逻辑：
   *  - 如果新文本以上次的开头（is prefix） → 还在扩展同一段，直接用新文本作为 committed+partial
   *  - 如果新文本不以上次开头但比上次短 → 上次的已完结，commit 上次，partial = 新
   *  - 如果上次为空 → partial = 新
   */
  _handleIncomingText(text, isFinal) {
    if (!text) return;
    if (!this._lastPartial) {
      this._lastPartial = text;
    } else if (text.startsWith(this._lastPartial) || this._lastPartial.startsWith(text)) {
      // 同一句的扩展：用更长的覆盖
      this._lastPartial = text.length >= this._lastPartial.length ? text : this._lastPartial;
    } else {
      // 不同句：之前的定型，新的开始
      this._committed += (this._committed ? ' ' : '') + this._lastPartial;
      this._lastPartial = text;
    }

    if (isFinal) {
      this._committed += (this._committed ? ' ' : '') + this._lastPartial;
      this._lastPartial = '';
    }

    this.transcript = (this._committed + (this._committed && this._lastPartial ? ' ' : '') + this._lastPartial).trim();
    if (isFinal) this.onFinal(this.transcript);
    else this.onPartial(this.transcript);
  }

  _cleanupStream() {
    try { this.stream && this.stream.getTracks().forEach(t => t.stop()); } catch (_) {}
    this.stream = null;
  }

  _cleanupAll() {
    try { this.workletNode && this.workletNode.disconnect(); } catch (_) {}
    try { this.source && this.source.disconnect(); } catch (_) {}
    try { this.audioCtx && this.audioCtx.close(); } catch (_) {}
    try { this.ws && this.ws.close(); } catch (_) {}
    this.workletNode = null;
    this.source = null;
    this.audioCtx = null;
    this.ws = null;
    this._cleanupStream();
  }
}
