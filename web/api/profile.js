// Profile 聚合视图 —— 技能档案 / 趋势 / 周报 / sync prompt
import { api } from './client.js';

export const profileApi = {
  getSkills:    ()         => api.get('/profile/skills'),
  getTrends:    (days = 30)=> api.get('/profile/trends', { days }),
  syncPrompt:   ()         => api.post('/profile:sync-prompt'),
  weeklyReport: ()         => api.post('/profile:weekly-report'),
};
