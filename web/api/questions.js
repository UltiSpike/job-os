// Question 资源 —— 仅 questions 表本身的字段
// answers / analyses / chat-sessions / topics 是独立资源，请用对应的 client
import { api } from './client.js';

export const questionsApi = {
  list:    (filters = {}) => api.get('/questions', filters),
  topics:  ()             => api.get('/questions/topics'),
  due:     ()             => api.get('/questions/due'),
  get:     (id)           => api.get(`/questions/${id}`),
  create:  (q)            => api.post('/questions', q),
  bulkCreate: (items)     => api.post('/questions/bulk', { items }),
  patch:   (id, p)        => api.patch(`/questions/${id}`, p),
  delete:  (id)           => api.delete(`/questions/${id}`),
  review:  (id, rating)   => api.post(`/questions/${id}/review`, { rating }),
  classify: (text, max_topics = 5) => api.post('/questions/classify', { text, max_topics }),

  // 流式 AI 出题
  generateStream(body, { onDelta } = {}) {
    const controller = new AbortController();
    const promise = (async () => {
      const res = await fetch('/api/v1/questions/generate', {
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
