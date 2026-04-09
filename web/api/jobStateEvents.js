// Job State Events —— 取代 job_states.stage_history JSON
import { api } from './client.js';

export const jobStateEventsApi = {
  list: (params = {}) => api.get('/job-state-events', params), // {job_id, days, limit}
};
