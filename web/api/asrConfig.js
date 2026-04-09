// ASR 配置 —— 独立 router
import { api } from './client.js';

export const asrConfigApi = {
  get:  ()         => api.get('/asr-config'),
  put:  (cfg)      => api.put('/asr-config', cfg),
  test: (overrides = {}) => api.post('/asr-config:test', overrides),
};
