import { html, raw } from '../components/html.js';
import { jobsStore } from '../store/jobs.js';
import { questionsStore } from '../store/questions.js';
import { profileApi } from '../api/profile.js';
import { clean, cleanTitle } from '../components/text.js';
import { fmtDate, daysSince } from '../components/dates.js';

let skillsCache = null;
let skillsLoading = false;
let trendsCache = null;
let weeklyReportCache = null;  // { text, generatedAt }
let weeklyReportLoading = false;

async function ensureSkills() {
  if (skillsCache || skillsLoading) return;
  skillsLoading = true;
  try {
    skillsCache = await profileApi.getSkills();
  } catch (_) {
    skillsCache = { strong: [], weak: [], recent_gaps: [], total_analyses: 0 };
  } finally {
    skillsLoading = false;
  }
}

async function ensureTrends() {
  if (trendsCache) return;
  try {
    trendsCache = await profileApi.getTrends(30);
  } catch (_) {
    trendsCache = { items: [], total: {} };
  }
}

async function generateWeeklyReport(rerender) {
  if (weeklyReportLoading) return;
  weeklyReportLoading = true;
  rerender();
  try {
    const r = await profileApi.weeklyReport();
    weeklyReportCache = { text: r.report, generatedAt: r.generated_at };
  } catch (e) {
    weeklyReportCache = { text: '✕ ' + e.message, generatedAt: null };
  }
  weeklyReportLoading = false;
  rerender();
}

export const decisionView = {
  name: 'decision',
  label: 'decision',

  render() {
    const { jobs, states, interviews, byTier } = jobsStore.state;
    const { questions, topics } = questionsStore.state;
    const stateList = Object.values(states);

    const funnel = {
      total: stateList.filter(s => s.intent !== 'ignored' && s.intent !== 'unknown').length,
      applied: stateList.filter(s => ['applied', 'contacting', 'interviewing', 'offer'].includes(s.pipeline_col)).length,
      iving: stateList.filter(s => s.pipeline_col === 'interviewing').length,
      offer: stateList.filter(s => s.pipeline_col === 'offer').length,
    };

    const recentIvs = [...interviews]
      .filter(iv => iv.time)
      .sort((a, b) => new Date(b.time) - new Date(a.time))
      .slice(0, 6);

    const jobMap = new Map(jobs.map(j => [j.href, j]));

    // weakest topics
    const weakTopics = Object.entries(topics)
      .filter(([, t]) => t.rated >= 2)
      .sort((a, b) => a[1].score - b[1].score)
      .slice(0, 5);

    return html`
      <section class="view view-decision">
        <header class="page-head">
          <div class="page-num">005 / DECISION</div>
          <h1 class="page-title">复盘<span class="accent">.</span></h1>
          <div class="page-meta">
            funnel · live<br>
            ${new Date().toLocaleDateString('zh-CN')}
          </div>
          <p class="page-lede">数据回看 — 哪些方向在推进，哪些技能要补，下一步往哪走。</p>
        </header>

        <div class="dec-grid">
          <div class="dec-card">
            <h4>◆ 漏斗 / Funnel</h4>
            <div class="lines">
              <div class="row"><span>P0 候选</span><span class="v">${(byTier.P0 || []).length}</span></div>
              <div class="row"><span>已关注</span><span class="v">${funnel.total}</span></div>
              <div class="row"><span>已投递</span><span class="v">${funnel.applied}</span></div>
              <div class="row"><span>面试中</span><span class="v">${funnel.iving}</span></div>
              <div class="row"><span>Offer</span><span class="v">${funnel.offer}</span></div>
            </div>
          </div>

          <div class="dec-card">
            <h4>◇ 训练强度</h4>
            <div class="lines">
              <div class="row"><span>题库总量</span><span class="v">${questions.length}</span></div>
              <div class="row"><span>已评估</span><span class="v">${questions.filter(q => q.rating).length}</span></div>
              <div class="row"><span>熟练 (good)</span><span class="v">${questions.filter(q => q.rating === 'good').length}</span></div>
              <div class="row"><span>一般 (ok)</span><span class="v">${questions.filter(q => q.rating === 'ok').length}</span></div>
              <div class="row"><span>不会 (bad)</span><span class="v">${questions.filter(q => q.rating === 'bad').length}</span></div>
            </div>
          </div>

          <div class="dec-card">
            <h4>◢ 弱项技能点</h4>
            <div class="lines">
              ${weakTopics.length === 0
                ? raw('<div class="dim mono" style="font-size:10px">还需要更多评分数据</div>')
                : raw(weakTopics.map(([n, t]) =>
                    `<div class="row"><span>${n}</span><span class="v">${Math.round(t.score * 100)}%</span></div>`
                  ).join(''))}
            </div>
          </div>
        </div>

        ${trendsCache && trendsCache.items && trendsCache.items.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◇</span>
              <h3>近 30 天活动趋势</h3>
              <span class="meta">${trendsCache.total.interviews || 0} 面试 · ${trendsCache.total.analyses || 0} 评估 · ${trendsCache.total.ratings || 0} 评分</span>
            </div>
            <div class="trends-chart">
              ${raw(renderTrendsChart(trendsCache.items))}
            </div>
          </section>
        ` : ''}

        <section class="sec">
          <div class="sec-head">
            <span class="sym">◆</span>
            <h3>本周复盘</h3>
            <span class="meta">AI 生成</span>
            <button class="btn ghost" data-gen-weekly style="margin-left:auto;font-size:10px;padding:5px 12px">${weeklyReportLoading ? '⋯ 生成中' : (weeklyReportCache ? '↻ 重新生成' : '✦ 生成本周复盘')}</button>
          </div>
          ${weeklyReportCache ? html`
            <div class="weekly-report">${weeklyReportCache.text}</div>
          ` : html`
            <div class="empty" style="padding:30px 0">点右侧按钮生成 — 基于本周的 stage 推进 / 面试 / 评估 / 评分数据，让 AI 写一段 250-400 字的复盘<span class="small">weekly retrospective</span></div>
          `}
        </section>

        ${skillsCache && (skillsCache.total_analyses > 0 || skillsCache.questions_practiced > 0) ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◢</span>
              <h3>技能档案</h3>
              <span class="meta">${skillsCache.total_analyses} 次评估 · ${skillsCache.questions_practiced} 题</span>
            </div>
            <div class="dec-grid">
              <div class="dec-card">
                <h4>◆ 强项</h4>
                <div class="lines">
                  ${skillsCache.strong.length === 0
                    ? raw('<div class="dim mono" style="font-size:10px">还需要更多评估数据</div>')
                    : raw(skillsCache.strong.slice(0, 6).map(s =>
                        `<div class="row"><span>${s.topic}</span><span class="v">${s.avg_score || '—'} · ${s.n}题</span></div>`
                      ).join(''))}
                </div>
              </div>
              <div class="dec-card">
                <h4>✗ 弱项</h4>
                <div class="lines">
                  ${skillsCache.weak.length === 0
                    ? raw('<div class="dim mono" style="font-size:10px">还没暴露明显弱项 — 继续练</div>')
                    : raw(skillsCache.weak.slice(0, 6).map(s =>
                        `<div class="row"><span>${s.topic}</span><span class="v" style="color:var(--rust)">${s.avg_score || '—'} · ${s.n}题</span></div>`
                      ).join(''))}
                </div>
              </div>
              <div class="dec-card">
                <h4>→ 最近 gaps</h4>
                <div class="lines">
                  ${skillsCache.recent_gaps.length === 0
                    ? raw('<div class="dim mono" style="font-size:10px">暂无</div>')
                    : raw(skillsCache.recent_gaps.slice(0, 6).map(g =>
                        `<div class="row" style="border-bottom-style:dotted"><span style="font-style:italic">${g}</span></div>`
                      ).join(''))}
                </div>
              </div>
            </div>
          </section>
        ` : ''}

        ${recentIvs.length > 0 ? html`
          <section class="sec">
            <div class="sec-head">
              <span class="sym">◇</span>
              <h3>最近面试</h3>
              <span class="meta">last ${recentIvs.length}</span>
            </div>
            <div class="upcoming">
              ${raw(recentIvs.map(iv => {
                const job = jobMap.get(iv.job_id);
                if (!job) return '';
                const past = daysSince(iv.time);
                return html`
                  <div class="upc">
                    <div class="upc-time">
                      <span class="big">${past}</span>
                      d ago
                    </div>
                    <div class="upc-info">
                      <div class="title">${iv.type} · ${cleanTitle(job.title)}</div>
                      <div class="meta">${clean(job.company)} <em>·</em> ${fmtDate(iv.time)} <em>·</em> ${iv.result || 'pending'}</div>
                    </div>
                  </div>
                `;
              }).join(''))}
            </div>
          </section>
        ` : ''}
      </section>
    `;
  },

  mount(root) {
    // 异步加载
    if (!skillsCache && !skillsLoading) {
      ensureSkills().then(() => {
        try { jobsStore.patch({ _skillsTick: Date.now() }); } catch (_) {}
      });
    }
    if (!trendsCache) {
      ensureTrends().then(() => {
        try { jobsStore.patch({ _skillsTick: Date.now() }); } catch (_) {}
      });
    }
    root.querySelector('[data-gen-weekly]')?.addEventListener('click', () => {
      generateWeeklyReport(() => {
        try { jobsStore.patch({ _skillsTick: Date.now() }); } catch (_) {}
      });
    });
  },
};

// 趋势图 — 简单 horizontal bar 用 CSS
function renderTrendsChart(items) {
  if (!items || items.length === 0) return '';
  const maxTotal = Math.max(1, ...items.map(d => d.interviews + d.analyses + d.ratings + d.transitions));
  // 显示最近 30 天，缺失天数补 0
  const today = new Date();
  const dateMap = {};
  for (const d of items) dateMap[d.date] = d;
  const days = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    days.push(dateMap[key] || { date: key, interviews: 0, analyses: 0, ratings: 0, transitions: 0 });
  }

  return `
    <div class="trends-grid">
      ${days.map(d => {
        const total = d.interviews + d.analyses + d.ratings + d.transitions;
        const pct = (total / maxTotal) * 100;
        const isToday = d.date === today.toISOString().slice(0, 10);
        const day = parseInt(d.date.slice(-2), 10);
        return `
          <div class="trends-day ${isToday ? 'today' : ''}" title="${d.date} · ${total} events (面 ${d.interviews} / 评 ${d.analyses} / 题 ${d.ratings} / 推 ${d.transitions})">
            <div class="trends-bar" style="height:${pct}%"></div>
            <div class="trends-lbl">${day}</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}
