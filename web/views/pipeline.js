import { html, raw, escapeAttr } from '../components/html.js';
import { jobsStore, setState, tierOf } from '../store/jobs.js';
import { clean, cleanTitle, cleanSalary } from '../components/text.js';
import { openInterviewModal, openInterviewEditModal } from './_interviewModal.js';
import { jobsApi } from '../api/jobs.js';
import { interviewsApi } from '../api/interviews.js';
import { jobStatesApi } from '../api/jobStates.js';
import { reloadInterviews, reloadJobStatesAndInterviews } from '../store/jobs.js';
import { openModal, closeModal } from '../components/modal.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';
import { fmtDate, daysSince } from '../components/dates.js';

const ACTIVE_COLS = [
  { key: 'todo',         name: '待投' },
  { key: 'applied',      name: '已投' },
  { key: 'contacting',   name: '联系中' },
  { key: 'interviewing', name: '面试中' },
  { key: 'offer',        name: 'Offer' },
];
const CLOSED_COL = { key: 'closed', name: '已结案' };

const INTENT_LABEL = {
  target:   '目标',
  practice: '练手',
  backup:   '备选',
  unknown:  '未决策',
  ignored:  '忽略',
};

let closedExpanded = false;

// ─── Pipeline 过滤系统 ───
// filter shape: { label, intents?, cols?, minStuckDays? }
let currentFilter = null;
let searchQuery = '';
let sortMode = 'stage'; // 'stage' (default) | 'urgent' | 'company' | 'recent'

export function setPipelineFilter(filter) {
  currentFilter = filter;
}

export function clearPipelineFilter() {
  currentFilter = null;
}

function applyFilter(cards) {
  let result = cards;
  if (currentFilter) {
    result = result.filter(({ st }) => {
      if (currentFilter.intents && !currentFilter.intents.includes(st.intent)) return false;
      if (currentFilter.cols && !currentFilter.cols.includes(st.pipeline_col)) return false;
      if (currentFilter.minStuckDays != null) {
        const days = ageDays(st.last_touch_at) || 0;
        if (days < currentFilter.minStuckDays) return false;
      }
      return true;
    });
  }
  if (searchQuery) {
    const q = searchQuery.toLowerCase();
    result = result.filter(({ job }) =>
      (job.title && job.title.toLowerCase().includes(q)) ||
      (job.company && job.company.toLowerCase().includes(q))
    );
  }
  // 排序
  if (sortMode === 'urgent') {
    result = [...result].sort((a, b) => (ageDays(b.st.last_touch_at) || 0) - (ageDays(a.st.last_touch_at) || 0));
  } else if (sortMode === 'company') {
    result = [...result].sort((a, b) => (a.job.company || '').localeCompare(b.job.company || ''));
  } else if (sortMode === 'recent') {
    result = [...result].sort((a, b) => (ageDays(a.st.last_touch_at) || 0) - (ageDays(b.st.last_touch_at) || 0));
  }
  return result;
}

function ageDays(iso) {
  return iso ? daysSince(iso) : null;
}

// 时间轴的 4 个里程碑顺序
const TIMELINE_NODES = [
  { key: 'todo',         short: '决' },
  { key: 'applied',      short: '投' },
  { key: 'contacting',   short: '联' },
  { key: 'interviewing', short: '面' },
  { key: 'offer',        short: '✓' },
];
const RESULT_GLYPH = { pass: '✓', fail: '✕', pending: '⋯' };

function renderMiniTimeline(st) {
  const events = jobsStore.state.eventsByJob[st.job_id] || [];
  // 已经"经过"过的 stage 集合 — 包括 from / to
  const visited = new Set([st.pipeline_col]);
  for (const ev of events) {
    if (ev.from_col) visited.add(ev.from_col);
    if (ev.to_col) visited.add(ev.to_col);
  }
  // closed 不在主线，不渲染
  const nodes = TIMELINE_NODES.filter(n => n.key !== 'closed');
  const dots = nodes.map((n, i) => {
    const isCurrent = n.key === st.pipeline_col;
    const isVisited = visited.has(n.key);
    const cls = isCurrent ? 'cur' : isVisited ? 'done' : 'todo';
    return `<span class="tl-dot ${cls}" title="${n.short}">${isCurrent ? '●' : isVisited ? '●' : '○'}</span>`;
  });
  // 用细线把点连起来
  const line = nodes.slice(0, -1).map((_, i) => '<span class="tl-line"></span>').join('');
  // interleave
  let html = '';
  for (let i = 0; i < dots.length; i++) {
    html += dots[i];
    if (i < dots.length - 1) html += '<span class="tl-line"></span>';
  }
  return `<div class="pl-timeline">${html}</div>`;
}

function renderIvChips(ivs) {
  if (!ivs || ivs.length === 0) return '';
  return `<div class="pl-iv-chips">${ivs.slice(0, 4).map(iv => {
    const result = iv.result || 'pending';
    return `<span class="pl-iv-chip iv-${result}" title="${escapeAttr(iv.type)} · ${RESULT_GLYPH[result]}">${escapeAttr(iv.type)}<span class="g">${RESULT_GLYPH[result]}</span></span>`;
  }).join('')}${ivs.length > 4 ? `<span class="pl-iv-more">+${ivs.length - 4}</span>` : ''}</div>`;
}

function cardHtml(job, st, ivs) {
  const tier = job._stale ? null : tierOf(job);
  const totalDays = ageDays(st.applied_at) ?? ageDays(st.triaged_at);
  const stageDays = ageDays(st.last_touch_at);
  const isStale = job._stale || (st.pipeline_col === 'applied' && (totalDays ?? 0) >= 5);
  const intent = st.intent || 'unknown';

  const metaParts = [];
  if (totalDays != null && st.pipeline_col !== 'todo') {
    metaParts.push(`<span class="m-age">投 ${totalDays} 天</span>`);
  }
  if (stageDays != null && stageDays > 0 && stageDays !== totalDays) {
    metaParts.push(`<span class="m-stage">停 ${stageDays} 天</span>`);
  }

  return `
    <div class="pl-card intent-${intent} ${isStale ? 'stale' : ''} ${job._stale ? 'orphan' : ''}" data-job="${escapeAttr(st.job_id)}" title="意图：${INTENT_LABEL[intent] || intent}">
      ${tier === 'P0' || tier === 'P1' ? `<span class="pl-tier tier-${tier}">${tier}</span>` : ''}
      ${job._stale ? '<span class="pl-tier" style="color:var(--rust)">!</span>' : ''}
      <div class="pl-title">${escapeAttr(cleanTitle(job.title))}</div>
      <div class="pl-company">${escapeAttr(clean(job.company))}</div>
      ${renderMiniTimeline(st)}
      ${renderIvChips(ivs)}
      ${metaParts.length > 0 ? `<div class="pl-meta">${metaParts.join(' <span class="sep">·</span> ')}</div>` : ''}
    </div>
  `;
}

function syntheticJob(jobId) {
  // 状态指向的岗位已不在当前 snapshot — 用 job_id 当 fallback
  // job_id 通常是 URL，截一段尾巴当 title
  let title = jobId;
  try {
    const u = new URL(jobId);
    title = u.pathname.split('/').filter(Boolean).pop() || u.host;
  } catch (_) {
    title = jobId.slice(-40);
  }
  return {
    href: jobId,
    title: '(已下线) ' + title,
    company: '—',
    salary: '',
    area: '',
    _stale: true,
  };
}

// Pipeline 只显示"主动管理中"的状态：target / practice / backup
// 排除 unknown（待 triage 的、退回 Discover 的）和 ignored（跳过的）
const PIPELINE_INTENTS = new Set(['target', 'practice', 'backup']);

function buildColData(jobMap, states, ivByJob) {
  const all = [...ACTIVE_COLS, CLOSED_COL].map(c => {
    let cards = Object.values(states)
      .filter(s => s.pipeline_col === c.key && PIPELINE_INTENTS.has(s.intent))
      .map(s => {
        const job = jobMap.get(s.job_id) || syntheticJob(s.job_id);
        const ivs = ivByJob[s.job_id] || [];
        return { job, st: s, ivs, html: cardHtml(job, s, ivs) };
      });
    cards = applyFilter(cards);
    return { ...c, cards, count: cards.length };
  });
  return all;
}

function computeMetrics(activeCols) {
  const byKey = Object.fromEntries(activeCols.map(c => [c.key, c.count]));
  const applied = byKey.applied || 0;
  const contact = byKey.contacting || 0;
  const iv = byKey.interviewing || 0;
  const offer = byKey.offer || 0;
  const totalApplied = applied + contact + iv + offer;
  const responded = contact + iv + offer;
  const respRate = totalApplied > 0 ? Math.round((responded / totalApplied) * 100) : 0;
  return {
    totalApplied,
    iv: iv + offer,
    offer,
    respRate,
    activeTotal: totalApplied + (byKey.todo || 0),
  };
}

function avgStaleness(states) {
  const list = Object.values(states).filter(s =>
    ['applied', 'contacting', 'interviewing'].includes(s.pipeline_col) && s.intent !== 'ignored'
  );
  if (list.length === 0) return null;
  const total = list.reduce((sum, s) => sum + (ageDays(s.last_touch_at) || 0), 0);
  return (total / list.length).toFixed(1);
}

function countStuck(states, threshold = 7) {
  return Object.values(states).filter(s =>
    ['applied', 'contacting', 'interviewing'].includes(s.pipeline_col)
    && s.intent !== 'ignored'
    && (ageDays(s.last_touch_at) || 0) >= threshold
  ).length;
}

export const pipelineView = {
  name: 'pipeline',
  label: 'pipeline',
  badge: () => {
    const { states } = jobsStore.state;
    return Object.values(states).filter(s => s.intent !== 'unknown' && s.intent !== 'ignored' && s.pipeline_col !== 'closed').length;
  },

  render() {
    const { jobs, states, interviews } = jobsStore.state;
    const jobMap = new Map(jobs.map(j => [j.href, j]));

    const ivByJob = {};
    for (const iv of interviews) {
      if (!ivByJob[iv.job_id]) ivByJob[iv.job_id] = [];
      ivByJob[iv.job_id].push(iv);
    }

    const allCols = buildColData(jobMap, states, ivByJob);
    const activeCols = allCols.filter(c => c.key !== 'closed');
    const closedCol = allCols.find(c => c.key === 'closed');
    const metrics = computeMetrics(activeCols);
    const stale = avgStaleness(states);
    const stuckCount = countStuck(states);

    // 漏斗条 — 显示 applied/contact/iv/offer 的相对宽度
    const funnelCols = activeCols.filter(c => c.key !== 'todo');
    const funnelMax = Math.max(1, ...funnelCols.map(c => c.count));
    const funnelHTML = funnelCols.map(c => {
      const w = (c.count / funnelMax) * 100;
      return `
        <div class="fl-seg fl-${c.key}" title="${c.desc}: ${c.count}">
          <div class="fl-bar" style="width:${w}%"></div>
          <div class="fl-label">${c.name} <strong>${c.count}</strong></div>
        </div>
      `;
    }).join('');

    // 列宽用 flex-grow 按数量加权（最少 140px，最多让大列吃饱）
    const totalActive = Math.max(1, activeCols.reduce((s, c) => s + c.count, 0));
    const colsHTML = activeCols.map(c => {
      const grow = Math.max(1, c.count);
      return `
        <div class="pl-col" style="flex: ${grow} 1 140px">
          <div class="pl-col-head">
            <span class="pl-col-name">${c.name}</span>
            <span class="pl-col-n">${c.count}</span>
          </div>
          <div class="pl-col-body">
            ${c.cards.length === 0
              ? '<div class="pl-empty">·</div>'
              : c.cards.map(c => c.html).join('')}
          </div>
        </div>
      `;
    }).join('');

    const filterChip = currentFilter ? html`
      <div class="pl-filter-bar">
        <span class="pl-filter-lbl mono">▸ 过滤</span>
        <span class="pl-filter-chip">${currentFilter.label}</span>
        <button class="pl-filter-clear" data-clear-filter>× 清除</button>
      </div>
    ` : '';

    const toolbar = html`
      <div class="pl-toolbar">
        <div class="pl-search">
          <span class="mono">⌕</span>
          <input id="pl-search-input" type="text" value="${searchQuery}" placeholder="搜索公司 / 职位">
          ${searchQuery ? '<button class="pl-search-clear" data-search-clear>×</button>' : ''}
        </div>
        <div class="pl-sort">
          <span class="mono">排序</span>
          <select id="pl-sort">
            <option value="stage" ${sortMode === 'stage' ? 'selected' : ''}>默认（按 stage）</option>
            <option value="urgent" ${sortMode === 'urgent' ? 'selected' : ''}>停滞最久优先</option>
            <option value="recent" ${sortMode === 'recent' ? 'selected' : ''}>最近活跃</option>
            <option value="company" ${sortMode === 'company' ? 'selected' : ''}>按公司名</option>
          </select>
        </div>
      </div>
    `;

    return html`
      <section class="view view-pipeline">
        <header class="page-head">
          <div class="page-num">003 / PIPELINE</div>
          <h1 class="page-title">流水线<span class="accent">.</span></h1>
          <div class="page-meta">
            ${metrics.activeTotal} 在管<br>
            ${closedCol.count} 已结案
          </div>
          <p class="page-lede">从待投递到 offer，每一格都是一次推进。颜色看意图，时间看停滞。</p>
        </header>

        ${filterChip}
        ${toolbar}

        <div class="pl-stats">
          <button class="pl-stat" data-stat-filter="applied">
            <div class="lbl">已投</div>
            <div class="num">${metrics.totalApplied}</div>
          </button>
          <button class="pl-stat" data-stat-filter="iving">
            <div class="lbl">面试中</div>
            <div class="num amber">${metrics.iv}</div>
          </button>
          <button class="pl-stat" data-stat-filter="offer">
            <div class="lbl">offer</div>
            <div class="num sage">${metrics.offer}</div>
          </button>
          <div class="pl-stat">
            <div class="lbl">回应率</div>
            <div class="num">${metrics.respRate}<span class="unit">%</span></div>
          </div>
          <div class="pl-stat">
            <div class="lbl">平均停滞</div>
            <div class="num ${stale && parseFloat(stale) >= 5 ? 'rust' : ''}">${stale ?? '—'}<span class="unit">天</span></div>
          </div>
          <button class="pl-stat" data-stat-filter="stuck">
            <div class="lbl">停滞 ≥7天</div>
            <div class="num ${stuckCount > 0 ? 'rust' : ''}">${stuckCount}</div>
          </button>
        </div>

        <div class="pl-funnel">
          ${raw(funnelHTML)}
        </div>

        <div class="pl-kanban">
          ${raw(colsHTML)}
        </div>

        <div class="pl-closed ${closedExpanded ? 'expanded' : ''}">
          <button class="pl-closed-toggle" data-toggle-closed>
            ${closedExpanded ? '▾' : '▸'} Closed <span class="n">${closedCol.count}</span>
          </button>
          ${closedExpanded ? raw(`
            <div class="pl-closed-body">
              ${closedCol.cards.length === 0
                ? '<div class="pl-empty">没有结案的岗位</div>'
                : closedCol.cards.map(c => c.html).join('')}
            </div>
          `) : ''}
        </div>
      </section>
    `;
  },

  mount(root) {
    root.querySelectorAll('[data-job]').forEach(el => {
      el.addEventListener('click', () => openJobModal(el.dataset.job));
    });
    root.querySelector('[data-toggle-closed]')?.addEventListener('click', () => {
      closedExpanded = !closedExpanded;
      router.refresh();
    });
    root.querySelector('[data-clear-filter]')?.addEventListener('click', () => {
      clearPipelineFilter();
      router.refresh();
    });
    // 顶部 stats 也可以点 → 各自加 filter
    root.querySelectorAll('[data-stat-filter]').forEach(el => {
      el.addEventListener('click', () => {
        const kind = el.dataset.statFilter;
        applyStatFilter(kind);
        router.refresh();
      });
    });
    // 搜索框
    const searchInput = root.querySelector('#pl-search-input');
    if (searchInput) {
      let debounce;
      searchInput.addEventListener('input', (e) => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          searchQuery = e.target.value;
          router.refresh();
          // 重新 focus
          setTimeout(() => {
            const el = document.querySelector('#pl-search-input');
            if (el) {
              el.focus();
              el.setSelectionRange(el.value.length, el.value.length);
            }
          }, 0);
        }, 250);
      });
    }
    root.querySelector('[data-search-clear]')?.addEventListener('click', () => {
      searchQuery = '';
      router.refresh();
    });
    // 排序
    root.querySelector('#pl-sort')?.addEventListener('change', (e) => {
      sortMode = e.target.value;
      router.refresh();
    });
  },
};

function applyStatFilter(kind) {
  if (kind === 'applied') setPipelineFilter({ label: '已投', cols: ['applied', 'contacting', 'interviewing', 'offer'] });
  else if (kind === 'iving') setPipelineFilter({ label: '面试中 / Offer', cols: ['interviewing', 'offer'] });
  else if (kind === 'offer') setPipelineFilter({ label: 'Offer', cols: ['offer'] });
  else if (kind === 'stuck') setPipelineFilter({ label: '停滞 ≥7 天', cols: ['applied', 'contacting', 'interviewing'], minStuckDays: 7 });
}

const STAGE_LABELS = {
  todo: '待投', applied: '已投', contacting: '联系中',
  interviewing: '面试中', offer: 'Offer', closed: '已结案',
};

// 时间线 — 把 stage_history 渲染成"叙事化事件流"
// 每条 history = 一个事件（推进/回退/面试），不是两个节点
function buildTimelineHtml(st, ivs) {
  const rawEvents = jobsStore.state.eventsByJob[st.job_id] || [];
  const stageOrder = ['todo', 'applied', 'contacting', 'interviewing', 'offer', 'closed'];

  // 收集事件
  const events = [];

  // 起点：决策（用 triaged_at；没有就用第一个 event 的 at）
  const startAt = st.triaged_at || (rawEvents[0]?.at) || null;
  if (startAt) {
    events.push({ kind: 'start', label: '决策', at: startAt, iv: null });
  }

  for (const h of rawEvents) {
    const fromIdx = stageOrder.indexOf(h.from_col);
    const toIdx = stageOrder.indexOf(h.to_col);
    let kind = 'forward';
    if (fromIdx >= 0 && toIdx >= 0) {
      if (toIdx > fromIdx) kind = 'forward';
      else if (toIdx < fromIdx) kind = 'back';
      else kind = 'same';
    }

    // 关联 interview — 用 interview_id 字段
    let iv = null;
    if (h.interview_id) {
      iv = ivs.find(x => x.id === h.interview_id) || null;
    }

    let label;
    if (iv) {
      label = `+ ${iv.type}`;
    } else {
      const stageName = STAGE_LABELS[h.to_col] || h.to_col;
      if (kind === 'forward') label = `推进到「${stageName}」`;
      else if (kind === 'back') label = `回退到「${stageName}」`;
      else label = `保持「${stageName}」`;
    }

    events.push({ kind, label, at: h.at, iv });
  }

  if (events.length === 0) {
    return '<div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);font-style:italic">暂无变化记录</div>';
  }

  // 渲染
  let prevAt = null;
  return `<div class="pl-tline">${events.map((ev, i) => {
    const date = ev.at ? new Date(ev.at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : '—';
    let dayDiff = null;
    if (i > 0 && ev.at && prevAt) {
      const d = Math.round((new Date(ev.at) - new Date(prevAt)) / 86400000);
      if (d > 0) dayDiff = d;
    }
    prevAt = ev.at || prevAt;

    const isLast = i === events.length - 1;
    const bulletMap = { start: '●', forward: '→', back: '↩', same: '↻' };
    const bullet = bulletMap[ev.kind] || '○';

    const ivResult = ev.iv ? (RESULT_GLYPH[ev.iv.result || 'pending']) : '';
    const ivCls = ev.iv ? `iv-${ev.iv.result || 'pending'}` : '';
    const dirCls = `dir-${ev.kind}`;

    return `
      <div class="pl-tline-row ${isLast ? 'last' : ''} ${ivCls} ${dirCls}">
        <span class="bullet">${bullet}</span>
        <span class="date">${date}</span>
        <span class="lbl">${escapeAttr(ev.label)}</span>
        <span class="diff">${dayDiff != null ? `+${dayDiff} 天` : ''}</span>
        <span class="result">${ivResult}</span>
      </div>
    `;
  }).join('')}</div>`;
}

function buildSmartActions(st, ivs) {
  const col = st.pipeline_col || 'todo';
  const buttons = [];
  if (col === 'todo') {
    buttons.push(`<button class="btn smart" data-smart="advance" data-to="applied">+ 标记已投</button>`);
    buttons.push(`<button class="btn smart" data-smart="add-iv" data-iv-type="一面">+ 直接进面</button>`);
  } else if (col === 'applied') {
    buttons.push(`<button class="btn smart" data-smart="advance" data-to="contacting">+ HR 已联系</button>`);
    buttons.push(`<button class="btn smart" data-smart="add-iv" data-iv-type="一面">+ 一面</button>`);
  } else if (col === 'contacting') {
    buttons.push(`<button class="btn smart" data-smart="add-iv" data-iv-type="一面">+ 一面</button>`);
  } else if (col === 'interviewing') {
    // 自动算下一面
    const ivCount = ivs.length;
    const ivNames = ['一面', '二面', '三面', '四面', '五面'];
    const next = ivNames[ivCount] || `${ivCount + 1} 面`;
    buttons.push(`<button class="btn smart" data-smart="add-iv" data-iv-type="${next}">+ ${next}</button>`);
    buttons.push(`<button class="btn smart" data-smart="advance" data-to="offer">拿到 offer</button>`);
    buttons.push(`<button class="btn smart danger" data-smart="advance" data-to="closed">挂了</button>`);
  } else if (col === 'offer') {
    buttons.push(`<button class="btn smart" data-smart="advance" data-to="closed">已结案</button>`);
  }
  // 通用：退回 Discover（任何 state 都可以）
  buttons.push(`<button class="btn smart ghost" data-smart="back-to-discover" style="margin-left:auto">⤺ 退回 Discover</button>`);
  return buttons.join('');
}

function openJobModal(jobId) {
  const { jobs, states, interviews } = jobsStore.state;
  const job = jobs.find(j => j.href === jobId);
  const st = states[jobId] || {};
  const ivs = interviews.filter(iv => iv.job_id === jobId).sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  if (!job) return;

  const RESULT_LABEL = { pending: '待定', pass: '通过', fail: '挂了' };
  const ivList = ivs.length === 0
    ? '<div style="color:var(--char-soft);font-family:var(--font-mono);font-size:11px">暂无面试</div>'
    : ivs.map(iv => `
        <div class="iv-item" data-iv="${iv.id}" style="padding:10px 0;border-bottom:1px dashed var(--line-paper-2);font-family:var(--font-mono);font-size:11px;color:var(--char-soft);position:relative">
          <div style="display:flex;align-items:center;gap:8px">
            <strong style="color:var(--char)">${iv.type}</strong>
            <span>· ${fmtDate(iv.time)}</span>
            ${iv.location ? `<span>· ${iv.location}</span>` : ''}
            <span class="iv-result iv-result-${iv.result || 'pending'}" style="margin-left:auto;padding:1px 6px;border:1px solid var(--line-paper-2);font-size:9px;letter-spacing:0.06em">${RESULT_LABEL[iv.result || 'pending']}</span>
            <button class="iv-act" data-iv-edit="${iv.id}" title="编辑" style="padding:2px 6px;border:1px solid var(--line-paper-2);background:transparent;color:var(--char-soft);font-family:inherit;font-size:10px;cursor:pointer">✎</button>
            <button class="iv-act" data-iv-del="${iv.id}" title="删除" style="padding:2px 6px;border:1px solid var(--line-paper-2);background:transparent;color:var(--char-soft);font-family:inherit;font-size:10px;cursor:pointer">✕</button>
          </div>
          ${iv.reflection ? `<div style="margin-top:6px;font-style:italic;font-family:var(--font-serif);font-size:13px;color:var(--char)">${iv.reflection}</div>` : ''}
        </div>
      `).join('');

  openModal({
    wide: true,
    title: cleanTitle(job.title),
    sub: `${clean(job.company)} · ${clean(job.area)} · ${cleanSalary(job.salary)}`,
    body: `
      <div class="pl-modal-row">
        <div class="field" style="flex:1">
          <label>状态</label>
          <select id="js-col">
            ${[...ACTIVE_COLS, CLOSED_COL].map(c => `<option value="${c.key}" ${st.pipeline_col === c.key ? 'selected' : ''}>${c.name}</option>`).join('')}
          </select>
        </div>
        <div class="field" style="flex:1">
          <label>意图</label>
          <select id="js-intent">
            ${['unknown', 'target', 'practice', 'backup', 'ignored'].map(i =>
              `<option value="${i}" ${st.intent === i ? 'selected' : ''}>${INTENT_LABEL[i]}</option>`
            ).join('')}
          </select>
        </div>
      </div>

      <div class="pl-smart-actions">
        ${buildSmartActions(st, ivs)}
      </div>

      <div class="pl-modal-section">
        <div class="pl-modal-section-h">◇ 时间线</div>
        ${buildTimelineHtml(st, ivs)}
      </div>

      <div class="field">
        <label>笔记</label>
        <textarea id="js-notes">${st.notes || ''}</textarea>
      </div>

      <div class="pl-modal-section">
        <div class="pl-modal-section-h">◇ 面试记录 (${ivs.length})</div>
        ${ivList}
      </div>
    `,
    actions: `
      ${job.href ? `<a class="btn" href="${job.href}" target="_blank" rel="noopener">原帖 ↗</a>` : ''}
      <button class="btn" id="js-add-iv">+ 面试</button>
      <button class="btn primary" id="js-save">保存</button>
    `,
    onMount(card) {
      card.querySelector('#js-save').addEventListener('click', async () => {
        try {
          await setState(jobId, {
            pipeline_col: card.querySelector('#js-col').value,
            intent: card.querySelector('#js-intent').value,
            notes: card.querySelector('#js-notes').value,
          });
          toast('已更新', 'success');
          closeModal();
          router.refresh();
        } catch (e) { toast(e.message, 'danger'); }
      });
      card.querySelector('#js-add-iv').addEventListener('click', () => {
        closeModal();
        openInterviewModal(jobId);
      });

      // ─── 智能快捷操作 ───
      card.querySelectorAll('[data-smart]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const action = btn.dataset.smart;
          if (action === 'advance') {
            const toCol = btn.dataset.to;
            const fromCol = st.pipeline_col;
            try {
              await setState(jobId, { pipeline_col: toCol });
              toast(`已推进到「${STAGE_LABELS[toCol]}」`, 'success');
              closeModal();
              router.refresh();
              openJobModal(jobId);
            } catch (e) { toast(e.message, 'danger'); }
          } else if (action === 'add-iv') {
            const ivType = btn.dataset.ivType;
            closeModal();
            openInterviewModal(jobId, { time: '', type: ivType });
          } else if (action === 'back-to-discover') {
            // 部分快照 —— events 是独立资源，重置后无法逐条还原；
            // 撤销只恢复 state 的标量字段（intent / pipeline_col / 时间戳 / notes）
            const snapshot = {
              intent: st.intent,
              pipeline_col: st.pipeline_col,
              applied_at: st.applied_at,
              triaged_at: st.triaged_at,
              notes: st.notes || '',
            };
            try {
              // jobStatesApi.reset 会清空 events + 重置标量
              await jobStatesApi.reset(jobId);
              await reloadJobStatesAndInterviews();
              closeModal();
              router.go('discover');
              undoableToast(`已退回 Discover`, async () => {
                await setState(jobId, snapshot);
                await reloadJobStatesAndInterviews();
                router.go('pipeline');
                toast('已恢复到 Pipeline（注意：历史 events 无法恢复）', 'success');
              }, { kind: 'success' });
            } catch (e) { toast(e.message, 'danger'); }
          }
        });
      });

      // 面试 编辑
      card.querySelectorAll('[data-iv-edit]').forEach(btn => {
        btn.addEventListener('click', () => {
          const ivId = parseInt(btn.dataset.ivEdit, 10);
          const iv = jobsStore.state.interviews.find(x => x.id === ivId);
          if (!iv) return;
          closeModal();
          openInterviewEditModal(iv, () => openJobModal(jobId));  // 编辑完重新打开父 modal
        });
      });

      // 面试 删除（带 undo）— 后端会同步回滚 stage_history + pipeline_col
      card.querySelectorAll('[data-iv-del]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const ivId = parseInt(btn.dataset.ivDel, 10);
          const iv = jobsStore.state.interviews.find(x => x.id === ivId);
          if (!iv) return;
          // 快照当前 state（用于撤销时还原 pipeline_col）
          const stSnapshot = { ...jobsStore.state.states[jobId] };
          try {
            await interviewsApi.delete(ivId);
            await reloadJobStatesAndInterviews(); // 同时拉 states + interviews
            closeModal();
            router.refresh();
            openJobModal(jobId);
            const titleHint = job ? cleanTitle(job.title).slice(0, 14) : '';
            undoableToast(`已删除面试「${iv.type}${titleHint ? ' · ' + titleHint : ''}」`, async () => {
              await interviewsApi.create(iv.job_id, {
                type: iv.type,
                time: iv.time,
                location: iv.location || '',
                result: iv.result || 'pending',
                reflection: iv.reflection || '',
              });
              // 撤销后端会自动 advance — 但 stSnapshot 才是真正的"删前状态"
              // 强制把 pipeline_col 还原回快照值
              await setState(jobId, {
                pipeline_col: stSnapshot.pipeline_col,
              });
              await reloadJobStatesAndInterviews();
              closeModal();
              router.refresh();
              openJobModal(jobId);
              toast('已恢复', 'success');
            }, { kind: 'success' });
          } catch (e) {
            toast('删除失败：' + e.message, 'danger');
          }
        });
      });
    },
  });
}
