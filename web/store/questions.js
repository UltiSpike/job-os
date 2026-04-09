import { createStore } from './createStore.js';
import { questionsApi } from '../api/questions.js';
import { analysesApi } from '../api/analyses.js';
import { answersApi } from '../api/answers.js';

export const questionsStore = createStore({
  questions: [],
  topics: {},
  // 跨题预聚合 — 给 today / decision dashboard 用
  recentAnalyses: [],         // [Analysis]
  answersByQuestion: {},      // { [qid]: [Answer] }
  loaded: false,
});

export async function loadQuestions() {
  const [list, topics, analyses, answersRes] = await Promise.all([
    questionsApi.list(),
    questionsApi.topics(),
    analysesApi.list({ limit: 500 }),
    answersApi.list({ limit: 500 }),
  ]);
  const answersByQuestion = {};
  for (const a of (answersRes.items || [])) {
    (answersByQuestion[a.question_id] ||= []).push(a);
  }
  questionsStore.patch({
    questions: list.items || [],
    topics: topics || {},
    recentAnalyses: analyses.items || [],
    answersByQuestion,
    loaded: true,
  });
}

export async function rateQuestion(id, rating) {
  await questionsApi.review(id, rating);
  await loadQuestions();
}

export async function createQuestion(q) {
  await questionsApi.create(q);
  await loadQuestions();
}

export async function deleteQuestion(id) {
  await questionsApi.delete(id);
  await loadQuestions();
}
