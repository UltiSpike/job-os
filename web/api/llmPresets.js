// LLM Preset 资源 —— 独立 router /llm-presets
import { api } from './client.js';

export const llmPresetsApi = {
  list:    ()         => api.get('/llm-presets'),
  get:     (name)     => api.get(`/llm-presets/${encodeURIComponent(name)}`),
  upsert:  (preset)   => api.post('/llm-presets', preset),
  patch:   (name, p)  => api.patch(`/llm-presets/${encodeURIComponent(name)}`, p),
  delete:  (name)     => api.delete(`/llm-presets/${encodeURIComponent(name)}`),
  activate:(name)     => api.post(`/llm-presets/${encodeURIComponent(name)}:activate`),
  test:    (name)     => api.post(`/llm-presets/${encodeURIComponent(name)}:test`),
};
