// Answer 资源 —— 取代 q.answer_variants
import { api } from './client.js';

export const answersApi = {
  list:    (params = {}) => api.get('/answers', params),
  listForQuestion: (qid) => api.get('/answers', { question_id: qid }),
  get:    (id)            => api.get(`/answers/${id}`),
  create: (body)          => api.post('/answers', body),  // {question_id, template_id, template_name, content}
  patch:  (id, content)   => api.patch(`/answers/${id}`, { content }),
  delete: (id)            => api.delete(`/answers/${id}`),
  restore: (snapshot)     => api.post('/answers/restore', snapshot),
};
