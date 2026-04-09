import { createStore } from './createStore.js';
import { llmPresetsApi } from '../api/llmPresets.js';
import { settingsApi, resumesApi } from '../api/settings.js';
import { asrConfigApi } from '../api/asrConfig.js';
import { promptTemplatesApi } from '../api/promptTemplates.js';

export const settingsStore = createStore({
  llmPresets: [],
  llmActive: null,
  asr: null,
  profile: null,
  prompts: [],
  resumes: [],
  loaded: false,
});

export async function loadSettings() {
  const [presets, asr, profile, prompts, resumes] = await Promise.all([
    llmPresetsApi.list(),
    asrConfigApi.get(),
    settingsApi.getProfile(),
    promptTemplatesApi.list(),
    resumesApi.list(),
  ]);
  settingsStore.patch({
    llmPresets: presets.items || [],
    llmActive: presets.active,
    asr,
    profile,
    prompts: prompts.items || [],
    resumes: resumes.items || [],
    loaded: true,
  });
}
