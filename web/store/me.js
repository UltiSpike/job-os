// User profile + mastery store — 单一真相源
// 任何 tab 显示 mastery / gap / today 推荐都从这里取
import { createStore } from './createStore.js';
import { meApi, conceptsApi } from '../api/me.js';

export const meStore = createStore({
  profile: null,
  mastery: [],            // [{ concept_slug, score, status, ... }]
  masteryBySlug: {},      // 同上 indexed by slug 方便查
  target: {},             // { concept_slug: weight }
  gap: [],
  coverage: { covered: 0, total: 0, percentage: 0, fallback: true },
  todayRec: null,
  concepts: [],
  conceptsBySlug: {},
  loaded: false,
});

export async function loadMe() {
  try {
    const [profile, mastery, target, gap, coverage, todayRec, concepts] = await Promise.all([
      meApi.get(),
      meApi.mastery(),
      meApi.target(),
      meApi.gap(),
      meApi.coverage(),
      meApi.todayRecommendation(),
      conceptsApi.list(),
    ]);
    const masteryItems = mastery.items || [];
    const conceptItems = concepts.items || [];
    meStore.patch({
      profile,
      mastery: masteryItems,
      masteryBySlug: Object.fromEntries(masteryItems.map(m => [m.concept_slug, m])),
      target: target.vector || {},
      gap: gap.items || [],
      coverage: coverage || { covered: 0, total: 0, percentage: 0, fallback: true },
      todayRec,
      concepts: conceptItems,
      conceptsBySlug: Object.fromEntries(conceptItems.map(c => [c.slug, c])),
      loaded: true,
    });
  } catch (e) {
    console.warn('loadMe failed (graceful degrade):', e.message);
    meStore.patch({ loaded: true });
  }
}

export async function patchMe(updates) {
  const profile = await meApi.patch(updates);
  meStore.patch({ profile });
  // updates 可能影响 target / gap / today，重新拉
  await loadMe();
  return profile;
}

// 局部刷新：在 practice/interview 后只重算 mastery + today，不动 profile
export async function refreshMastery() {
  try {
    const [mastery, gap, coverage, todayRec] = await Promise.all([
      meApi.mastery(), meApi.gap(), meApi.coverage(), meApi.todayRecommendation(),
    ]);
    const items = mastery.items || [];
    meStore.patch({
      mastery: items,
      masteryBySlug: Object.fromEntries(items.map(m => [m.concept_slug, m])),
      gap: gap.items || [],
      coverage,
      todayRec,
    });
  } catch (e) {
    console.warn('refreshMastery failed:', e.message);
  }
}

// 工具：根据 lesson_slug 找 concept 的 mastery（lesson_slug == concept_slug）
export function getMasteryForLesson(lessonSlug) {
  return meStore.state.masteryBySlug[lessonSlug] || null;
}

// 工具：根据 concept_slug 找它属于哪个 track/module 用于跳转 URL
export function getCurriculumUrl(conceptSlug) {
  const c = meStore.state.conceptsBySlug[conceptSlug];
  if (!c) return '#/curriculum';
  const parts = ['curriculum'];
  if (c.track_slug) parts.push(c.track_slug);
  if (c.module_slug) parts.push(c.module_slug);
  parts.push(conceptSlug);
  return '#/' + parts.join('/');
}
