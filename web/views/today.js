import { html, raw, escapeAttr, escapeHtml } from '../components/html.js';
import { jobsStore, jobId } from '../store/jobs.js';
import { questionsStore } from '../store/questions.js';
import { meStore } from '../store/me.js';
import { fmtDate, daysSince, hoursUntil, fmtRelativeFuture } from '../components/dates.js';
import { clean, cleanTitle } from '../components/text.js';
import { router } from '../app.js';
import { openInterviewModal } from './_interviewModal.js';
import { setPipelineFilter } from './pipeline.js';
import { llmApi } from '../api/llm.js';
import { toast } from '../components/toast.js';

// 模块状态：早间简报缓存（避免每次切回 today 都重新调 LLM）
let briefingCache = null; // { text, generatedAt }
let briefingState = 'idle'; // 'idle' | 'streaming' | 'done' | 'error'

// 智能截断 — 中文按标点 / 括号断句，避免半截字
function smartTruncate(s, max = 22) {
  if (!s) return '';
  s = String(s).replace(/\s+/g, ' ').trim();
  if (s.length <= max) return s;
  // 优先在标点处截断
  const punct = ['(', '（', ' ', '·', '/', '-', '|', '，', '、'];
  for (let i = max; i > max * 0.6; i--) {
    if (punct.includes(s[i])) return s.slice(0, i) + '…';
  }
  return s.slice(0, max) + '…';
}

const STAGE_ZH = { todo: '待投', applied: '已投', contacting: '联系中', interviewing: '面试中', offer: 'Offer', closed: '已结案' };
const RATING_ZH = { good: '熟练', ok: '一般', bad: '不会' };

// 派生：从现有数据 derive 最近 7 天活动
function deriveRecentActivity() {
  const { interviews, states, jobs } = jobsStore.state;
  const { questions } = questionsStore.state;
  const now = Date.now();
  const sevenDaysAgo = now - 7 * 86400000;
  const events = [];
  const jobMap = new Map(jobs.map(j => [j.href, j]));

  // ─ 1. interviews 创建
  for (const iv of interviews) {
    const at = iv.created_at ? new Date(iv.created_at).getTime() : 0;
    if (at < sevenDaysAgo) continue;
    const job = jobMap.get(iv.job_id);
    const title = job ? smartTruncate(cleanTitle(job.title), 18) : iv.job_id.slice(-20);
    events.push({
      at,
      kind: 'interview',
      icon: '▸',
      iconCls: 'amber',
      verb: '记录了',
      object: `${iv.type}`,
      target: title,
      sub: job?.company ? clean(job.company) : '',
      jobId: iv.job_id,
      to: 'pipeline',
    });
  }

  // ─ 2. job state events（排除 interview-driven —— #1 已 cover）
  const stageOrder = ['todo', 'applied', 'contacting', 'interviewing', 'offer', 'closed'];
  for (const [jobId, evList] of Object.entries(jobsStore.state.eventsByJob || {})) {
    for (const h of evList) {
      const at = h.at ? new Date(h.at).getTime() : 0;
      if (at < sevenDaysAgo) continue;
      if (h.interview_id) continue;
      const job = jobMap.get(jobId);
      const title = job ? smartTruncate(cleanTitle(job.title), 18) : jobId.slice(-20);
      const fromIdx = stageOrder.indexOf(h.from_col);
      const toIdx = stageOrder.indexOf(h.to_col);
      let verb, icon, iconCls;
      if (toIdx > fromIdx) { verb = '推进到'; icon = '→'; iconCls = 'sage'; }
      else if (toIdx < fromIdx) { verb = '回退到'; icon = '↩'; iconCls = 'rust'; }
      else { verb = '保持'; icon = '↻'; iconCls = 'amber'; }
      events.push({
        at,
        kind: 'stage',
        icon,
        iconCls,
        verb,
        object: `「${STAGE_ZH[h.to_col] || h.to_col}」`,
        target: title,
        sub: job?.company ? clean(job.company) : '',
        jobId,
        to: 'pipeline',
      });
    }
  }

  // ─ 3. AI 评估 —— 走 store 的 recentAnalyses
  const qById = new Map(questions.map(q => [q.id, q]));
  for (const a of (questionsStore.state.recentAnalyses || [])) {
    const at = a.at ? new Date(a.at).getTime() : 0;
    if (at < sevenDaysAgo) continue;
    const q = qById.get(a.question_id);
    if (!q) continue;
    events.push({
      at,
      kind: 'analysis',
      icon: '◇',
      iconCls: a.score >= 80 ? 'sage' : a.score >= 60 ? 'amber' : 'rust',
      verb: 'AI 评估',
      object: `${a.score ?? '—'} 分`,
      target: smartTruncate(q.text, 26),
      sub: (a.gaps || [])[0] ? `缺口: ${smartTruncate((a.gaps || [])[0], 30)}` : '',
      questionId: q.id,
      to: 'training',
    });
  }

  // ─ 4. 题目评分
  for (const q of questions) {
    if (q.last_reviewed_at) {
      const at = new Date(q.last_reviewed_at).getTime();
      if (at < sevenDaysAgo) continue;
      const r = q.rating;
      events.push({
        at,
        kind: 'rating',
        icon: '●',
        iconCls: r === 'good' ? 'sage' : r === 'ok' ? 'amber' : r === 'bad' ? 'rust' : 'dim',
        verb: '自评为',
        object: `「${RATING_ZH[r] || r || '?'}」`,
        target: smartTruncate(q.text, 26),
        sub: '',
        questionId: q.id,
        to: 'training',
      });
    }
  }

  // ─ 5. AI 生成的答案 —— 走 store 的 answersByQuestion
  const ansByQ = questionsStore.state.answersByQuestion || {};
  for (const [qid, ansList] of Object.entries(ansByQ)) {
    const q = qById.get(qid);
    if (!q) continue;
    for (const v of ansList) {
      const at = v.generated_at ? new Date(v.generated_at).getTime() : 0;
      if (at < sevenDaysAgo) continue;
      events.push({
        at,
        kind: 'variant',
        icon: '✦',
        iconCls: 'amber',
        verb: 'AI 生成',
        object: `「${v.template_name}」答案`,
        target: smartTruncate(q.text, 26),
        sub: v.user_edited ? '后续手动编辑过' : '',
        questionId: q.id,
        to: 'training',
      });
    }
  }

  events.sort((a, b) => b.at - a.at);
  return events;
}

// 把 events 按天分组
function groupByDay(events) {
  const groups = new Map();  // dayKey → { label, events }
  const todayKey = new Date().toISOString().slice(0, 10);
  const yesterdayKey = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  for (const ev of events) {
    const d = new Date(ev.at);
    const key = d.toISOString().slice(0, 10);
    if (!groups.has(key)) {
      let label;
      if (key === todayKey) label = '今天';
      else if (key === yesterdayKey) label = '昨天';
      else {
        const diff = Math.floor((Date.now() - new Date(key).getTime()) / 86400000);
        label = `${diff} 天前`;
      }
      groups.set(key, { label, key, dateText: d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }), events: [] });
    }
    groups.get(key).events.push(ev);
  }
  return [...groups.values()];
}

// 派生：连续活跃天数 streak
function computeStreak() {
  const events = deriveRecentActivity().concat([]);  // copy
  // 跨更长时间窗口算 streak
  const { interviews, states } = jobsStore.state;
  const { questions } = questionsStore.state;
  const allDates = new Set();
  const stamp = (iso) => {
    if (!iso) return;
    const d = new Date(iso);
    if (isNaN(d)) return;
    allDates.add(d.toISOString().slice(0, 10));
  };
  for (const iv of interviews) stamp(iv.created_at);
  for (const evList of Object.values(jobsStore.state.eventsByJob || {})) {
    for (const e of evList) stamp(e.at);
  }
  for (const q of questions) stamp(q.last_reviewed_at);
  for (const a of (questionsStore.state.recentAnalyses || [])) stamp(a.at);
  // 从今天往前数
  let streak = 0;
  let cursor = new Date();
  while (true) {
    const key = cursor.toISOString().slice(0, 10);
    if (allDates.has(key)) {
      streak++;
      cursor.setDate(cursor.getDate() - 1);
    } else {
      // 今天没活跃也算 0 而不是断
      if (streak === 0 && key === new Date().toISOString().slice(0, 10)) {
        cursor.setDate(cursor.getDate() - 1);
        continue;
      }
      break;
    }
  }
  return streak;
}

// 触发 AI 早间简报
async function generateBriefing(rerender) {
  briefingState = 'streaming';
  briefingCache = { text: '', generatedAt: new Date().toISOString() };
  rerender();

  const { jobs, states, interviews } = jobsStore.state;
  const stateList = Object.values(states);
  const upcoming = (interviews || [])
    .map(iv => ({ iv, h: hoursUntil(iv.time) }))
    .filter(x => x.h >= 0 && x.h <= 72);
  const followup = stateList
    .filter(s => s.pipeline_col === 'applied')
    .filter(s => daysSince(s.applied_at || s.last_touch_at) >= 3);
  const triageCount = jobs.filter(j => !states[j.href] || states[j.href].intent === 'unknown').length;
  const stuck = stateList.filter(s =>
    ['applied', 'contacting', 'interviewing'].includes(s.pipeline_col)
    && (daysSince(s.last_touch_at) || 0) >= 7
  );

  const ctx = `今日待办上下文（${new Date().toLocaleString('zh-CN')}）：
- 即将到来面试: ${upcoming.length} 个 ${upcoming.length > 0 ? '(' + upcoming.slice(0, 3).map(u => u.iv.type).join('、') + ')' : ''}
- 需跟进岗位: ${followup.length} 个 (投递 ≥3 天没动)
- 停滞 ≥7 天: ${stuck.length} 个
- 待决策新岗位: ${triageCount} 个
- 已投递总数: ${stateList.filter(s => ['applied','contacting','interviewing','offer'].includes(s.pipeline_col)).length}
`;

  try {
    const handle = llmApi.chatStream([
      { role: 'system', content: `你是一名资深求职教练，每天早上给候选人一段简短的"今日聚焦"建议。
要求：
- 第一句给出今天最该做的一件事（最高优先级）
- 第二句指出一个潜在风险或要补的功课
- 第三句鼓励但不空洞
- 全文 80-150 字，纯文本无 markdown，自然口语
- 不要用"早上好"等寒暄开场，直接进入正题
- 不要列举 bullet，用自然的句子` },
      { role: 'user', content: ctx },
    ], {
      temperature: 0.6,
      onDelta: (_, full) => {
        briefingCache.text = full;
        rerender();
      },
    });
    await handle.promise;
    briefingState = 'done';
    rerender();
  } catch (e) {
    briefingState = 'error';
    briefingCache = { text: '生成失败：' + e.message, generatedAt: new Date().toISOString() };
    rerender();
  }
}

export const todayView = {
  name: 'today',
  label: 'today',

  render() {
    const { jobs, states, interviews } = jobsStore.state;
    const stateList = Object.values(states);

    // upcoming (next 72h)
    const jobMap = new Map(jobs.map(j => [j.href, j]));
    const upcoming = (interviews || [])
      .map(iv => ({ iv, job: jobMap.get(iv.job_id), h: hoursUntil(iv.time) }))
      .filter(x => x.job && x.h >= 0 && x.h <= 72)
      .sort((a, b) => a.h - b.h);

    // followups: applied >= 3 days
    const followup = stateList
      .filter(s => s.pipeline_col === 'applied')
      .map(s => ({ s, job: jobMap.get(s.job_id), days: daysSince(s.applied_at || s.last_touch_at) }))
      .filter(x => x.job && x.days >= 3)
      .sort((a, b) => b.days - a.days)
      .slice(0, 6);

    const stats = {
      target: stateList.filter(s => s.intent === 'target').length,
      practice: stateList.filter(s => s.intent === 'practice').length,
      iving: stateList.filter(s => s.pipeline_col === 'interviewing' || s.pipeline_col === 'offer').length,
      pending: stateList.filter(s => s.pipeline_col === 'applied' || s.pipeline_col === 'contacting').length,
    };

    const triageCount = jobs.filter(j => !states[j.href] || states[j.href].intent === 'unknown').length;

    const hour = new Date().getHours();
    const greet = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好';
    const weekdayZh = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date().getDay()];

    // 派生数据
    const recentActivity = deriveRecentActivity();
    const activityGroups = groupByDay(recentActivity);
    const streak = computeStreak();
    const dueQuestions = (questionsStore.state.questions || []).filter(q => {
      if (!q.next_review_at) return true;
      return new Date(q.next_review_at).getTime() <= Date.now();
    });

    return html`
      <section class="view view-today">
        <header class="page-head">
          <div class="page-num">001 / TODAY</div>
          <h1 class="page-title">${greet}<span class="accent">.</span></h1>
          <div class="page-meta">
            ${new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })}<br>
            ${weekdayZh}
          </div>
          <p class="page-lede">每一日的求职操作台 — 看面试、追跟进、清待办。</p>
        </header>

        ${(() => {
          const rec = meStore.state.todayRec;
          const cov = meStore.state.coverage;
          if (!rec || rec.kind === 'empty') return '';
          const covLabel = (cov && !cov.fallback && cov.total > 0)
            ? `<span class="today-rec-cov">目标覆盖度 ${Math.round((cov.percentage || 0) * 100)}% (${cov.covered}/${cov.total})</span>`
            : '';
          return raw(`
            <a class="today-rec" href="${rec.url || '#/today'}">
              <div class="today-rec-left">
                <div class="today-rec-kind">${rec.kind}</div>
                <div class="today-rec-label">${escapeHtml(rec.label)}</div>
              </div>
              <div class="today-rec-right">
                ${covLabel}
                <span class="today-rec-arrow">▶</span>
              </div>
            </a>
          `);
        })()}

        <div class="today-stats">
          <button class="stat" data-stat-jump="target"><div class="label">目标 // target</div><div class="num amber">${stats.target}</div></button>
          <button class="stat" data-stat-jump="practice"><div class="label">练手 // practice</div><div class="num">${stats.practice}</div></button>
          <button class="stat" data-stat-jump="iving"><div class="label">面试中 // active</div><div class="num">${stats.iving}</div></button>
          <button class="stat" data-stat-jump="pending"><div class="label">待回应 // pending</div><div class="num ${stats.pending > 5 ? 'rust' : ''}">${stats.pending}</div></button>
        </div>

        <section class="today-briefing">
          <div class="brief-head">
            <span class="sym">◆</span>
            <span class="brief-title">今日聚焦</span>
            ${streak > 0 ? raw(`<span class="brief-streak">▸ 连续 ${streak} 天活跃</span>`) : ''}
            <button class="brief-gen-btn" data-gen-brief>${briefingState === 'streaming' ? '⋯ 生成中' : (briefingCache ? '↻ 重新生成' : '✦ AI 建议')}</button>
          </div>
          ${briefingCache ? raw(`
            <div class="brief-body ${briefingState === 'streaming' ? 'streaming' : ''}">${escapeHtml(briefingCache.text)}</div>
          `) : raw(`
            <div class="brief-empty">点击右上「✦ AI 建议」让 AI 根据你今天的状态给出 2-3 句聚焦建议</div>
          `)}
        </section>

        ${upcoming.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◆</span>
              <h3>即将到来的面试</h3>
              <span class="meta">next 72h · ${upcoming.length}</span>
            </div>
            <div class="upcoming">
              ${raw(upcoming.map(({ iv, job, h }) => {
                const cls = h < 6 ? 'imminent' : h < 24 ? '' : 'relaxed';
                return html`
                  <div class="upc">
                    <div class="upc-time ${cls}">
                      <span class="big">${fmtRelativeFuture(iv.time)}</span>
                      ${fmtDate(iv.time)}
                    </div>
                    <div class="upc-info">
                      <div class="title">${iv.type} <em>·</em> ${cleanTitle(job.title)}</div>
                      <div class="meta">${clean(job.company)}${iv.location ? ` <em>·</em> ${clean(iv.location)}` : ''}</div>
                    </div>
                    <button class="btn" data-go="pipeline">查看 →</button>
                  </div>
                `;
              }).join(''))}
            </div>
          </section>
        ` : ''}

        ${followup.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◇</span>
              <h3>需要跟进</h3>
              <span class="meta">applied ≥ 3d · ${followup.length}</span>
            </div>
            <div class="followup">
              ${raw(followup.map(({ s, job, days }) => {
                const cls = days >= 7 ? 'danger' : days >= 5 ? 'warn' : '';
                return html`
                  <div class="fup">
                    <div class="fup-days ${cls}">
                      <span class="big">${days}</span>
                      days
                    </div>
                    <div class="fup-info">
                      <div class="title">${cleanTitle(job.title)}</div>
                      <div class="meta">${clean(job.company)} · 投于 ${fmtDate(s.applied_at)}</div>
                    </div>
                    <div class="btn-row">
                      ${job.href ? html`<a class="btn ghost" href="${job.href}" target="_blank" rel="noopener">戳 HR ↗</a>` : ''}
                      <button class="btn primary" data-add-iv="${escapeAttr(s.job_id)}">+ 面试</button>
                    </div>
                  </div>
                `;
              }).join(''))}
            </div>
          </section>
        ` : ''}

        ${triageCount > 0 ? html`
          <section class="sec">
            <div class="triage-cta">
              <div>
                <h4>新岗位待 triage</h4>
                <p>共 <span class="num">${triageCount}</span> 个未决策 — 用 Discover 一张张分流</p>
              </div>
              <button class="btn primary" data-go="discover">开始 triage →</button>
            </div>
          </section>
        ` : ''}

        ${dueQuestions.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◇</span>
              <h3>今日复习</h3>
              <span class="meta">due · ${dueQuestions.length}</span>
            </div>
            <div class="triage-cta">
              <div>
                <h4>题库里有 ${dueQuestions.length} 道题到期</h4>
                <p>间隔复习把你之前评过的题推回桌面 — 别让肌肉记忆掉</p>
              </div>
              <button class="btn primary" data-go-training>开始复习 →</button>
            </div>
          </section>
        ` : ''}

        ${recentActivity.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◇</span>
              <h3>最近活动</h3>
              <span class="meta">last 7d · ${recentActivity.length}</span>
            </div>
            <div class="today-activity">
              ${raw(activityGroups.slice(0, 5).map(group => `
                <div class="act-day-group">
                  <div class="act-day-head">
                    <span class="act-day-lbl">${escapeHtml(group.label)}</span>
                    <span class="act-day-date mono">${group.dateText}</span>
                    <span class="act-day-count mono">${group.events.length} 条</span>
                  </div>
                  ${group.events.map(ev => {
                    const t = new Date(ev.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
                    const dataAttr = ev.questionId ? `data-act-q="${escapeHtml(ev.questionId)}"` :
                                     ev.jobId ? `data-act-job="${escapeHtml(ev.jobId)}"` : '';
                    return `
                      <div class="act-row" ${dataAttr}>
                        <span class="act-time mono">${t}</span>
                        <span class="act-icon ${ev.iconCls || ''}">${ev.icon}</span>
                        <div class="act-body">
                          <div class="act-line">
                            <span class="act-verb">${escapeHtml(ev.verb)}</span>
                            <span class="act-obj">${escapeHtml(ev.object)}</span>
                            <span class="act-sep">·</span>
                            <span class="act-target">${escapeHtml(ev.target)}</span>
                          </div>
                          ${ev.sub ? `<div class="act-sub mono">${escapeHtml(ev.sub)}</div>` : ''}
                        </div>
                        <span class="act-arrow">→</span>
                      </div>
                    `;
                  }).join('')}
                </div>
              `).join(''))}
            </div>
          </section>
        ` : ''}

        ${upcoming.length === 0 && followup.length === 0 && triageCount === 0 && recentActivity.length === 0 ? html`
          <div class="empty">所有任务都跟上了。<span class="small">all clear</span></div>
        ` : ''}
      </section>
    `;
  },

  mount(root) {
    root.querySelectorAll('[data-go]').forEach(el => {
      el.addEventListener('click', () => router.go(el.dataset.go));
    });
    root.querySelectorAll('[data-add-iv]').forEach(el => {
      el.addEventListener('click', () => openInterviewModal(el.dataset.addIv));
    });
    // 点 stats 跳到 Pipeline filter
    root.querySelectorAll('[data-stat-jump]').forEach(el => {
      el.addEventListener('click', () => {
        const k = el.dataset.statJump;
        if (k === 'target')   setPipelineFilter({ label: '意图：目标', intents: ['target'] });
        else if (k === 'practice') setPipelineFilter({ label: '意图：练手', intents: ['practice'] });
        else if (k === 'iving')    setPipelineFilter({ label: '面试中 / Offer', cols: ['interviewing', 'offer'] });
        else if (k === 'pending')  setPipelineFilter({ label: '待回应（已投/联系中）', cols: ['applied', 'contacting'] });
        router.go('pipeline');
      });
    });
    // 早间简报
    root.querySelector('[data-gen-brief]')?.addEventListener('click', () => {
      if (briefingState === 'streaming') return;
      generateBriefing(() => router.refresh());
    });
    // 复习快捷入口
    root.querySelector('[data-go-training]')?.addEventListener('click', () => {
      router.go('training');
    });
    // 活动行点击跳转
    root.querySelectorAll('[data-act-q]').forEach(el => {
      el.addEventListener('click', () => router.go('training'));
    });
    root.querySelectorAll('[data-act-job]').forEach(el => {
      el.addEventListener('click', () => router.go('pipeline'));
    });
  },
};
