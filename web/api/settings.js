// Settings —— 仅个人 profile（angle/role/target/system_prompt 等）
// ASR 配置 / Prompt 模板 / LLM Preset 已经各自独立 client
import { api } from './client.js';

export const settingsApi = {
  getProfile: () => api.get('/settings/profile'),
  putProfile: (p) => api.put('/settings/profile', p),
};

export const resumesApi = {
  list:    ()           => api.get('/resumes'),
  get:     (id)         => api.get(`/resumes/${id}`),
  create:  (body)       => api.post('/resumes', body),
  patch:   (id, p)      => api.patch(`/resumes/${id}`, p),
  delete:  (id)         => api.delete(`/resumes/${id}`),
};
