import { createStore } from './createStore.js';
import { jobsApi } from '../api/jobs.js';
import { jobStatesApi } from '../api/jobStates.js';
import { interviewsApi } from '../api/interviews.js';
import { jobStateEventsApi } from '../api/jobStateEvents.js';

export const jobsStore = createStore({
  jobs: [],          // 完整 snapshot 列表
  byTier: {},        // { P0: [...], P1: [...], ... }
  states: {},        // { [job_id]: state }
  interviews: [],    // 全部面试
  eventsByJob: {},   // { [job_id]: JobStateEvent[] } —— 取代旧的 stage_history JSON
  loaded: false,
  error: null,
});

export async function loadJobs() {
  try {
    const [allRes, statesRes, ivRes, evRes, byTier] = await Promise.all([
      jobsApi.list(),
      jobStatesApi.list(),
      interviewsApi.list(),
      jobStateEventsApi.list({ days: 3650 }),  // 全量
      Promise.all(['P0', 'P1', 'P2', 'P3'].map(t => jobsApi.listByTier(t).then(r => [t, r.items]))),
    ]);
    const stateMap = {};
    for (const s of statesRes.items || []) stateMap[s.job_id] = s;
    const eventsByJob = {};
    for (const e of (evRes.items || [])) {
      (eventsByJob[e.job_id] ||= []).push(e);
    }
    // 升序，跟旧的 stage_history 一致
    for (const k in eventsByJob) {
      eventsByJob[k].sort((a, b) => (a.at || '').localeCompare(b.at || ''));
    }
    jobsStore.patch({
      jobs: allRes.items || [],
      states: stateMap,
      interviews: ivRes.items || [],
      eventsByJob,
      byTier: Object.fromEntries(byTier),
      loaded: true,
      error: null,
    });
  } catch (e) {
    jobsStore.patch({ error: e.message });
    throw e;
  }
}

export function getState(jobId) {
  return jobsStore.state.states[jobId] || {
    job_id: jobId,
    intent: 'unknown',
    pipeline_col: 'todo',
    outcome: null,
  };
}

export async function setState(jobId, patch) {
  const updated = await jobStatesApi.patch(jobId, patch);
  const newStates = { ...jobsStore.state.states, [jobId]: updated };
  jobsStore.patch({ states: newStates });
  return updated;
}

export async function loadJobStates() {
  const r = await jobStatesApi.list();
  const m = {};
  for (const s of r.items || []) m[s.job_id] = s;
  jobsStore.patch({ states: m });
}

export async function reloadInterviews() {
  const r = await interviewsApi.list();
  jobsStore.patch({ interviews: r.items || [] });
}

export async function reloadJobStatesAndInterviews() {
  const [statesRes, ivRes, evRes] = await Promise.all([
    jobStatesApi.list(),
    interviewsApi.list(),
    jobStateEventsApi.list({ days: 3650 }),
  ]);
  const m = {};
  for (const s of statesRes.items || []) m[s.job_id] = s;
  const eventsByJob = {};
  for (const e of (evRes.items || [])) {
    (eventsByJob[e.job_id] ||= []).push(e);
  }
  for (const k in eventsByJob) {
    eventsByJob[k].sort((a, b) => (a.at || '').localeCompare(b.at || ''));
  }
  jobsStore.patch({ states: m, interviews: ivRes.items || [], eventsByJob });
}

export async function addInterview(jobId, iv) {
  const created = await interviewsApi.create(jobId, iv);
  await reloadJobStatesAndInterviews();
  return created;
}

export function jobId(j) {
  return j.href || `${j.company}|${j.title}`;
}

export function tierOf(job) {
  const bt = jobsStore.state.byTier;
  for (const t of ['P0', 'P1', 'P2', 'P3']) {
    if ((bt[t] || []).some(j => j.href === job.href)) return t;
  }
  return 'P3';
}
