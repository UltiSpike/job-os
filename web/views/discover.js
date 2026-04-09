import { html, raw, escapeAttr } from '../components/html.js';
import { jobsStore, getState, setState, tierOf } from '../store/jobs.js';
import { questionsStore } from '../store/questions.js';
import { settingsStore } from '../store/settings.js';
import { clean, cleanTitle, cleanJD, cleanSalary } from '../components/text.js';
import { escapeHtml } from '../components/html.js';
import { renderPager, bindPagerScrubber } from '../components/pagination.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';

let filter = 'P0';
let expandedId = null;
let pageIdx = 0;
let pageSize = 30;

const CORE_CLUSTERS = ['platform_ai_infra', 'go_k8s_platform', 'gpu_cloud_platform'];

// 派生：用户的「强项关键词」用于 JD 高亮
// 来源：profile.role/target、所有题库的 topics、cluster_hits 的 display
function getUserKeywords() {
  const set = new Set();
  // profile
  const profile = settingsStore.state.profile;
  if (profile) {
    for (const f of [profile.role, profile.target, profile.experience]) {
      if (f) {
        for (const w of String(f).split(/[\s,，、\/]/)) {
          if (w.length >= 2) set.add(w);
        }
      }
    }
  }
  // 题库 topics
  for (const q of (questionsStore.state.questions || [])) {
    for (const t of (q.topics || [])) {
      if (t.length >= 2) set.add(t);
    }
  }
  // 一些常见关键词手动补充
  const baseKeywords = ['k8s', 'kubernetes', 'go', 'golang', 'gpu', '云原生', '调度', '分布式', 'docker'];
  for (const k of baseKeywords) set.add(k);
  return [...set];
}

function highlightJD(text, keywords) {
  if (!text || keywords.length === 0) return escapeHtml(text || '');
  // 转义 + 高亮
  let html = escapeHtml(text);
  // 按长度倒序匹配（避免短关键词覆盖长关键词）
  const sorted = [...keywords].sort((a, b) => b.length - a.length);
  for (const kw of sorted) {
    if (!kw) continue;
    const escapedKw = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedKw})`, 'gi');
    html = html.replace(regex, '<mark class="jd-hl">$1</mark>');
  }
  return html;
}

function getQueue() {
  const { jobs, byTier } = jobsStore.state;
  let queue;
  if (filter === 'kept') {
    // 已关注但未投：intent != unknown/ignored 且 col == todo
    queue = jobs.filter(j => {
      const s = getState(j.href);
      return s.intent !== 'unknown' && s.intent !== 'ignored' && s.pipeline_col === 'todo';
    });
  } else if (filter === 'ignored') {
    // 已忽略 — 让用户找回
    queue = jobs.filter(j => getState(j.href).intent === 'ignored');
  } else {
    queue = jobs.filter(j => getState(j.href).intent === 'unknown');
    if (filter === 'P0') queue = queue.filter(j => (byTier.P0 || []).some(x => x.href === j.href));
    else if (filter === 'P1') queue = queue.filter(j => (byTier.P1 || []).some(x => x.href === j.href));
    else if (filter === 'high') queue = queue.filter(j => (j.final_score || 0) >= 50);
  }
  queue.sort((a, b) => (b.final_score || 0) - (a.final_score || 0));
  return queue;
}

function row(job, idx) {
  const id = job.href;
  const tier = tierOf(job);
  const isExp = expandedId === id;
  const isIgnored = filter === 'ignored';
  const clusters = (job.cluster_hits || []).slice(0, 2).map(h => {
    const isCore = CORE_CLUSTERS.includes(h.name);
    return `<span class="cluster-chip ${isCore ? 'core' : ''}">${h.display}</span>`;
  }).join('');
  const keywords = getUserKeywords();
  const jdText = cleanJD(job.jd || '暂无 JD').slice(0, 1800);
  const highlightedJD = highlightJD(jdText, keywords);
  const detail = isExp ? html`
    <div class="inbox-detail">
      <div class="jd">${raw(highlightedJD)}</div>
      <div class="id-actions">
        ${job.href ? html`<a class="btn" href="${job.href}" target="_blank" rel="noopener" data-stop>原帖 ↗</a>` : ''}
        ${isIgnored
          ? html`<button class="btn primary" data-restore="${escapeAttr(id)}">↺ 取消忽略</button>`
          : html`<button class="btn" data-skip="${escapeAttr(id)}">✕ 跳过</button>
                 <button class="btn primary" data-keep="${escapeAttr(id)}">◯ 关注</button>`}
      </div>
    </div>
  ` : '';

  return html`
    <div class="inbox-row ${isExp ? 'expanded' : ''}" data-toggle="${escapeAttr(id)}">
      <div class="ir-idx">${String(idx + 1).padStart(3, '0')}</div>
      <div class="ir-score tier-${tier}">${(job.final_score || 0).toFixed(0)}</div>
      <div class="ir-main">
        <div class="title">${cleanTitle(job.title)} <span class="dim mono" style="font-size:10px;margin-left:8px">${cleanSalary(job.salary)}</span></div>
        <div class="clusters">${raw(clusters)}</div>
      </div>
      <div class="ir-company">${clean(job.company)}</div>
      <div class="ir-area">${clean(job.area).slice(0, 14)}</div>
      <div class="ir-actions">
        ${raw(isIgnored
          ? `<button class="btn primary" data-restore="${escapeAttr(id)}" data-stop title="取消忽略">↺</button>`
          : `<button class="btn" data-skip="${escapeAttr(id)}" data-stop>✕</button>
             <button class="btn primary" data-keep="${escapeAttr(id)}" data-stop>◯</button>`)}
      </div>
    </div>
    ${detail}
  `;
}

export const discoverView = {
  name: 'discover',
  label: 'discover',
  badge: () => {
    const { jobs, states } = jobsStore.state;
    return jobs.filter(j => !(states[j.href] && states[j.href].intent !== 'unknown')).length;
  },

  render() {
    const queue = getQueue();
    const filters = [
      ['P0', 'P0 必投'], ['P1', 'P1 应投'], ['high', '高分 ≥50'], ['all', '全部'], ['kept', '已关注未投'], ['ignored', '已忽略'],
    ];
    const totalPages = Math.max(1, Math.ceil(queue.length / pageSize));
    if (pageIdx >= totalPages) pageIdx = totalPages - 1;
    if (pageIdx < 0) pageIdx = 0;
    const start = pageIdx * pageSize;
    const end = Math.min(start + pageSize, queue.length);
    const paged = queue.slice(start, end);

    return html`
      <section class="view view-discover">
        <header class="page-head">
          <div class="page-num">002 / DISCOVER</div>
          <h1 class="page-title">分流<span class="accent">.</span></h1>
          <div class="page-meta">
            queue · ${queue.length}<br>
            filter · ${filter}
          </div>
          <p class="page-lede">把陌生的岗位逐一过一遍 — 关注、跳过，决策即轻盈。</p>
        </header>

        <div class="discover-toolbar">
          ${raw(filters.map(([k, label]) =>
            `<button class="dt-filter ${filter === k ? 'active' : ''}" data-filter="${k}">${label}</button>`
          ).join(''))}
          <span class="dt-counter">${queue.length} · 待决策</span>
        </div>

        ${queue.length === 0 ? html`
          <div class="empty">当前过滤下没有待决策的岗位<span class="small">try another filter</span></div>
        ` : html`
          <div class="inbox">
            ${raw(paged.map((j, i) => row(j, start + i)).join(''))}
          </div>
          ${totalPages > 1 ? raw(renderPager({
            pageIdx,
            total: totalPages,
            count: queue.length,
            range: [start, end],
            prefix: 'data-dpage',
            label: 'jobs',
          })) : ''}
        `}
      </section>
    `;
  },

  mount(root) {
    root.querySelectorAll('[data-filter]').forEach(el => {
      el.addEventListener('click', () => {
        filter = el.dataset.filter;
        expandedId = null;
        pageIdx = 0;  // 切 filter 时重置分页
        router.refresh();
      });
    });
    const totalPagesNow = Math.max(1, Math.ceil(getQueue().length / pageSize));
    const jumpToPage = (idx) => {
      pageIdx = Math.max(0, Math.min(idx, totalPagesNow - 1));
      expandedId = null;
      router.refresh();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    root.querySelectorAll('[data-dpage]').forEach(el => {
      el.addEventListener('click', () => {
        const dir = el.dataset.dpage;
        if (dir === 'prev') jumpToPage(pageIdx - 1);
        else if (dir === 'next') jumpToPage(pageIdx + 1);
      });
    });
    bindPagerScrubber(root, 'data-dpage', totalPagesNow, jumpToPage);
    root.querySelectorAll('[data-toggle]').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('[data-stop]')) return;
        const id = el.dataset.toggle;
        expandedId = expandedId === id ? null : id;
        router.refresh();
      });
    });
    root.querySelectorAll('[data-skip]').forEach(el => {
      el.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = el.dataset.skip;
        // 备份当前 state，用于撤销
        const before = { ...getState(id) };
        const job = jobsStore.state.jobs.find(j => j.href === id);
        const label = job ? `${cleanTitle(job.title).slice(0, 14)} · ${clean(job.company)}` : id.slice(-30);
        try {
          await setState(id, { intent: 'ignored', triaged_at: new Date().toISOString() });
          if (expandedId === id) expandedId = null;
          router.refresh();
          undoableToast(`已忽略「${label}」`, async () => {
            await setState(id, {
              intent: before.intent || 'unknown',
              pipeline_col: before.pipeline_col || 'todo',
              triaged_at: before.triaged_at || null,
            });
            router.refresh();
            toast('已恢复', 'success');
          }, { timeout: 4000, kind: 'success' });
        } catch (err) { toast(err.message, 'danger'); }
      });
    });
    root.querySelectorAll('[data-keep]').forEach(el => {
      el.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = el.dataset.keep;
        try {
          await setState(id, { intent: 'backup', pipeline_col: 'todo', triaged_at: new Date().toISOString() });
          toast('已加入 Pipeline 待投递', 'success');
          if (expandedId === id) expandedId = null;
          router.refresh();
        } catch (err) { toast(err.message, 'danger'); }
      });
    });
    root.querySelectorAll('[data-restore]').forEach(el => {
      el.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = el.dataset.restore;
        try {
          await setState(id, {
            intent: 'unknown',
            pipeline_col: 'todo',
            triaged_at: null,
          });
          if (expandedId === id) expandedId = null;
          router.refresh();
          toast('已取消忽略，回到 inbox', 'success');
        } catch (err) { toast(err.message, 'danger'); }
      });
    });
  },
};
