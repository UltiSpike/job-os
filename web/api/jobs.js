// Jobs 资源 —— 只读 snapshot 数据
// JobState / Interview / JobStateEvent 已经拆到独立 client
import { api } from './client.js';

export const jobsApi = {
  list:        ()        => api.get('/jobs'),
  listByTier:  (tier)    => api.get('/jobs', { tier }),
  get:         (id)      => api.get(`/jobs/${encodeURIComponent(id)}`),
};
