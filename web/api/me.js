// /me + /concepts API client
import { api } from './client.js';

export const meApi = {
  get:                ()       => api.get('/me'),
  patch:              (body)   => api.patch('/me', body),
  mastery:            ()       => api.get('/me/mastery'),
  target:             ()       => api.get('/me/target'),
  gap:                ()       => api.get('/me/gap'),
  coverage:           ()       => api.get('/me/coverage'),
  todayRecommendation:()       => api.get('/me/today-recommendation'),
};

export const conceptsApi = {
  list:    (track) => api.get('/concepts', track ? { track } : undefined),
  get:     (slug)  => api.get(`/concepts/${slug}`),
  mastery: (slug)  => api.get(`/concepts/${slug}/mastery`),
};
