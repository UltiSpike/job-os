// Analysis 资源 —— 取代 q.analyses
import { api } from './client.js';

export const analysesApi = {
  listForQuestion: (qid)        => api.get('/analyses', { question_id: qid }),
  list:    (params = {})        => api.get('/analyses', params),
  get:     (id)                 => api.get(`/analyses/${id}`),
  create:  (body)               => api.post('/analyses', body),
  delete:  (id)                 => api.delete(`/analyses/${id}`),
  restore: (snapshot)           => api.post('/analyses/restore', snapshot),

  // 流式生成 — onDelta(text, full) 回调累积文本
  stream(body, { onDelta } = {}) {
    const controller = new AbortController();
    const promise = (async () => {
      const res = await fetch('/api/v1/analyses:stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
            const delta = obj.choices?.[0]?.delta?.content ?? obj.choices?.[0]?.message?.content ?? '';
            if (delta) {
              full += delta;
              try { onDelta && onDelta(delta, full); } catch (_) {}
            }
          } catch (_) {}
        }
      }
      return full;
    })();
    return { promise, abort: () => controller.abort() };
  },
};
