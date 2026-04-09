// Curriculum: tracks / modules / lessons / progress
import { api } from './client.js';

export const curriculumApi = {
  listTracks:    ()      => api.get('/tracks'),
  getTrack:      (slug)  => api.get(`/tracks/${slug}`),
  getTrackTree:  (slug)  => api.get(`/tracks/${slug}/tree`),
  listModules:   (track) => api.get('/modules', { track }),
  listLessons:   (mod)   => api.get('/lessons', { module: mod }),
  getLesson:     (slug)  => api.get(`/lessons/${slug}`),
  listProgress:  ()      => api.get('/lesson-progress'),
  putProgress:   (slug, body) => api.put(`/lesson-progress/${slug}`, body),
  ensureCapstoneQuestion: (slug) => api.post(`/lessons/${slug}/capstone-question`, {}),
};

export const resumeProfilesApi = {
  extract:       (rid)        => api.post(`/resumes/${rid}:extract-profile`, {}),
  listForResume: (rid)        => api.get('/resume-profiles', { resume_id: rid }),
  get:           (pid)        => api.get(`/resume-profiles/${pid}`),
  delete:        (pid)        => api.delete(`/resume-profiles/${pid}`),
};

export const studyPlansApi = {
  create:        (body)       => api.post('/study-plans', body),
  listForProfile:(pid)        => api.get('/study-plans', { resume_profile_id: pid }),
  get:           (pid)        => api.get(`/study-plans/${pid}`),
};

export const interviewTopicsApi = {
  add:           (body)       => api.post('/interview-topics', body),
  list:          (q)          => api.get('/interview-topics', q),
  delete:        (id)         => api.delete(`/interview-topics/${id}`),
};
