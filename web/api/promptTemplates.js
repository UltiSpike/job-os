// Prompt 模板 —— 独立 router
import { api } from './client.js';

export const promptTemplatesApi = {
  list:   ()           => api.get('/prompt-templates'),
  get:    (id)         => api.get(`/prompt-templates/${encodeURIComponent(id)}`),
  upsert: (body)       => api.post('/prompt-templates', body),
  patch:  (id, body)   => api.patch(`/prompt-templates/${encodeURIComponent(id)}`, body),
  delete: (id)         => api.delete(`/prompt-templates/${encodeURIComponent(id)}`),
};
