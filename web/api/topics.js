// Topics 资源 + question_topics 关联
import { api } from './client.js';

export const topicsApi = {
  list:    ()      => api.get('/topics'),
  stats:   ()      => api.get('/topics:stats'),
  get:     (id)    => api.get(`/topics/${id}`),

  // 某个 question 的 topics
  forQuestion: (qid)         => api.get(`/questions/${qid}/topics`),
  setForQuestion: (qid, ids) => api.put(`/questions/${qid}/topics`, { topic_ids: ids }),
};
