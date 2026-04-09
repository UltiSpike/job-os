// LLM 直接调用代理 —— 仅 chat / chat-stream / test
// Presets CRUD 已经独立到 web/api/llm.presets.js (llmPresetsApi)
import { api } from './client.js';

export const llmApi = {
  test: (body = {}) => api.post('/llm/test', body),

  chat: (messages, opts = {}) =>
    api.post('/llm/chat', {
      messages,
      preset: opts.preset || null,
      temperature: opts.temperature ?? 0.5,
    }),

  // 流式 chat —— 返回 { promise, abort }
  chatStream(messages, { onDelta, temperature = 0.6, preset = null } = {}) {
    const controller = new AbortController();
    const promise = (async () => {
      const res = await fetch('/api/v1/llm/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, temperature, preset, stream: true }),
        signal: controller.signal,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (!data) continue;
          if (data === '[DONE]') return full;
          try {
            const obj = JSON.parse(data);
            if (obj.error) throw new Error(obj.error);
            const delta =
              obj.choices?.[0]?.delta?.content ??
              obj.choices?.[0]?.message?.content ??
              '';
            if (delta) {
              full += delta;
              try { onDelta && onDelta(delta, full); } catch (_) {}
            }
          } catch (e) {
            if (e.name === 'AbortError') throw e;
          }
        }
      }
      return full;
    })();
    return { promise, abort: () => controller.abort() };
  },
};
