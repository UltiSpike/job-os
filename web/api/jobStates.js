// Job State 资源（与 Job 拆分；Job 是只读 snapshot 数据，State 是用户的进度）
import { api } from './client.js';

export const jobStatesApi = {
  list:   ()                => api.get('/job-states'),
  get:    (jobId)           => api.get(`/job-states/${encodeURIComponent(jobId)}`),
  patch:  (jobId, body)     => api.patch(`/job-states/${encodeURIComponent(jobId)}`, body),
  delete: (jobId)           => api.delete(`/job-states/${encodeURIComponent(jobId)}`),
  reset:  (jobId)           => api.post(`/job-states/${encodeURIComponent(jobId)}:reset`),
};
