// 面试资源 —— 扁平，不再嵌套于 jobs
import { api } from './client.js';

export const interviewsApi = {
  list:   (jobId)        => api.get('/interviews', jobId ? { job_id: jobId } : null),
  get:    (id)           => api.get(`/interviews/${id}`),
  create: (jobId, body)  => api.post('/interviews', { job_id: jobId, ...body }),
  patch:  (id, body)     => api.patch(`/interviews/${id}`, body),
  delete: (id)           => api.delete(`/interviews/${id}`),
};
