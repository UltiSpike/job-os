import { html, raw, escapeAttr, escapeHtml } from '../components/html.js';
import { extractTopicsLocal } from '../lib/topicMatcher.js';
import { renderPager, bindPagerScrubber } from '../components/pagination.js';
import { questionsStore, loadQuestions, rateQuestion, createQuestion, deleteQuestion } from '../store/questions.js';
import { questionsApi } from '../api/questions.js';
import { openModal, closeModal } from '../components/modal.js';
import { openPractice } from './_practiceModal.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';
import { meStore, getCurriculumUrl } from '../store/me.js';
import { curriculumStore } from '../store/curriculum.js';

let topicFilter = null;     // null = all
let ratingFilter = 'all';   // all | due | unrated | bad | ok | good
let pageIdx = 0;            // 当前页（0-based）
let pageSize = 20;          // 每页大小

const RATING_FILTERS = [
  ['all', '全部'],
  ['due', '今日到期'],
  ['unrated', '未评'],
  ['bad', '不会'],
  ['ok', '一般'],
  ['good', '熟练'],
];

function isDue(q) {
  if (!q.next_review_at) return true;
  return new Date(q.next_review_at).getTime() <= Date.now();
}

function topicScore(t) {
  // 0..1 — used for bar fill width
  return Math.round((t.score || 0) * 100);
}

export const trainingView = {
  name: 'training',
  label: 'training',
  badge: () => {
    return (questionsStore.state.questions || []).filter(isDue).length;
  },

  render() {
    const { questions, topics } = questionsStore.state;

    let filtered = [...questions];
    if (topicFilter) filtered = filtered.filter(q => (q.topics || []).includes(topicFilter));
    if (ratingFilter === 'due') filtered = filtered.filter(isDue);
    else if (ratingFilter === 'unrated') filtered = filtered.filter(q => !q.rating);
    else if (ratingFilter !== 'all') filtered = filtered.filter(q => q.rating === ratingFilter);

    // 分页
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    if (pageIdx >= totalPages) pageIdx = totalPages - 1;
    if (pageIdx < 0) pageIdx = 0;
    const pagedFiltered = filtered.slice(pageIdx * pageSize, (pageIdx + 1) * pageSize);

    const topicEntries = Object.entries(topics)
      .sort((a, b) => b[1].total - a[1].total);

    return html`
      <section class="view view-training">
        <header class="page-head">
          <div class="page-num">004 / TRAINING</div>
          <h1 class="page-title">训练场<span class="accent">.</span></h1>
          <div class="page-meta">
            questions · ${questions.length}<br>
            due · ${questions.filter(isDue).length}
          </div>
          <p class="page-lede">每一题都是一次拷打 — 看自己哪里站得稳，哪里需要补。</p>
        </header>

        <div class="training-grid">
          <aside class="tr-side">
            <h4>◇ 技能点 / Topics</h4>
            <div class="topic-row ${topicFilter === null ? 'active' : ''}" data-topic="">
              <span>全部</span>
              <span class="n">${questions.length}</span>
            </div>
            ${raw(topicEntries.map(([name, t]) => `
              <div class="topic-row ${topicFilter === name ? 'active' : ''}" data-topic="${escapeAttr(name)}">
                <span>${name}</span>
                <span class="bar" style="--w:${topicScore(t)}%"></span>
                <span class="n">${t.total}</span>
              </div>
            `).join(''))}
            <button class="btn add-q" data-add-q>+ 新增题目</button>
            <button class="btn add-q" data-ai-gen-q style="margin-top:6px">✦ AI 出题</button>
          </aside>

          <main class="tr-main">
            <div class="tr-filter-bar">
              ${raw(RATING_FILTERS.map(([k, label]) =>
                `<button class="tr-filter ${ratingFilter === k ? 'active' : ''}" data-rfilter="${k}">${label}</button>`
              ).join(''))}
              <button class="btn primary" data-practice style="margin-left:auto;margin-bottom:8px">▶ 进入练习 (${filtered.length})</button>
            </div>

            ${filtered.length === 0 ? html`
              <div class="empty">没有匹配的题目<span class="small">add or change filter</span></div>
            ` : html`
              <div class="q-list">
                ${raw(pagedFiltered.map(q => qItem(q)).join(''))}
              </div>
              ${totalPages > 1 ? raw(renderPager({
                pageIdx,
                total: totalPages,
                count: filtered.length,
                range: [pageIdx * pageSize, Math.min((pageIdx + 1) * pageSize, filtered.length)],
                prefix: 'data-tpage',
                label: 'questions',
              })) : ''}
            `}
          </main>
        </div>
      </section>
    `;
  },

  mount(root) {
    root.querySelectorAll('[data-topic]').forEach(el => {
      el.addEventListener('click', () => {
        topicFilter = el.dataset.topic || null;
        pageIdx = 0;  // 切换 filter 时重置到第一页
        router.refresh();
      });
    });
    root.querySelectorAll('[data-rfilter]').forEach(el => {
      el.addEventListener('click', () => {
        ratingFilter = el.dataset.rfilter;
        pageIdx = 0;
        router.refresh();
      });
    });
    const totalPagesNow = Math.max(1, Math.ceil(currentFiltered().length / pageSize));
    const jumpToPage = (idx) => {
      pageIdx = Math.max(0, Math.min(idx, totalPagesNow - 1));
      router.refresh();
      window.scrollTo({ top: document.querySelector('.q-list')?.offsetTop - 100 || 0, behavior: 'smooth' });
    };
    root.querySelectorAll('[data-tpage]').forEach(el => {
      el.addEventListener('click', () => {
        const dir = el.dataset.tpage;
        if (dir === 'prev') jumpToPage(pageIdx - 1);
        else if (dir === 'next') jumpToPage(pageIdx + 1);
      });
    });
    bindPagerScrubber(root, 'data-tpage', totalPagesNow, jumpToPage);
    root.querySelectorAll('[data-rate]').forEach(el => {
      el.addEventListener('click', async () => {
        const [id, r] = el.dataset.rate.split('|');
        try {
          await rateQuestion(id, r);
          toast(`已评 ${r}`, 'success');
          router.refresh();
        } catch (e) { toast(e.message, 'danger'); }
      });
    });
    root.querySelectorAll('[data-del-q]').forEach(el => {
      el.addEventListener('click', async () => {
        const id = el.dataset.delQ;
        // 先拿一份完整快照备份（用于撤销）
        const snapshot = questionsStore.state.questions.find(q => q.id === id);
        if (!snapshot) return;
        try {
          await deleteQuestion(id);
          undoableToast(`已删除「${(snapshot.text || '').slice(0, 20)}」`, async () => {
            // 重建：用 snapshot 的所有字段还原
            await questionsApi.create({
              text: snapshot.text,
              topics: snapshot.topics || [],
              source: snapshot.source || 'manual',
              answer: snapshot.answer,
              note: snapshot.note || '',
            });
            await loadQuestions();
            router.refresh();
            toast('已恢复', 'success');
          }, { kind: 'success' });
        } catch (e) { toast(e.message, 'danger'); }
      });
    });

    root.querySelectorAll('[data-edit-q]').forEach(el => {
      el.addEventListener('click', () => {
        const q = questionsStore.state.questions.find(x => x.id === el.dataset.editQ);
        if (q) openEditQuestionModal(q);
      });
    });

    root.querySelector('[data-add-q]')?.addEventListener('click', openAddQuestionModal);
    root.querySelector('[data-ai-gen-q]')?.addEventListener('click', openAIGenerateModal);

    root.querySelector('[data-practice]')?.addEventListener('click', () => {
      const queue = currentFiltered();
      openPractice(queue, 0);
    });

    root.querySelectorAll('[data-practice-one]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = el.dataset.practiceOne;
        const all = questionsStore.state.questions;
        const idx = all.findIndex(q => q.id === id);
        if (idx >= 0) openPractice(all, idx);
      });
    });
  },
};

// 复用 render 里的过滤逻辑
function currentFiltered() {
  const { questions } = questionsStore.state;
  let filtered = [...questions];
  if (topicFilter) filtered = filtered.filter(q => (q.topics || []).includes(topicFilter));
  if (ratingFilter === 'due') filtered = filtered.filter(isDue);
  else if (ratingFilter === 'unrated') filtered = filtered.filter(q => !q.rating);
  else if (ratingFilter !== 'all') filtered = filtered.filter(q => q.rating === ratingFilter);
  return filtered;
}

function qItem(q) {
  const ratingSym = q.rating === 'good' ? '●' : q.rating === 'ok' ? '◐' : q.rating === 'bad' ? '○' : '·';
  const ratingCls = q.rating || '';
  // 派生 hidden 数据
  const variants = Array.isArray(q.answer_variants) ? q.answer_variants : [];
  const analyses = Array.isArray(q.analyses) ? q.analyses : [];
  let totalFollowups = 0;
  for (const v of variants) {
    if (Array.isArray(v.followups)) totalFollowups += Math.floor(v.followups.length / 2) || v.followups.length;
  }
  const lastScore = analyses.length > 0 ? analyses[analyses.length - 1].score : null;
  const avgScore = analyses.length > 0
    ? Math.round(analyses.reduce((s, a) => s + (a.score || 0), 0) / analyses.length)
    : null;

  // 元数据 chips
  const dataChips = [];
  if (variants.length > 0) {
    dataChips.push(`<span class="q-data-chip" title="已生成的答案模板数">▸ ${variants.length} 答</span>`);
  }
  if (totalFollowups > 0) {
    dataChips.push(`<span class="q-data-chip" title="追问轮数">💬 ${totalFollowups}</span>`);
  }
  if (analyses.length > 0) {
    const cls = avgScore >= 80 ? 'high' : avgScore >= 60 ? 'mid' : 'low';
    dataChips.push(`<span class="q-data-chip score ${cls}" title="平均评估分">◇ ${avgScore}/100 · ${analyses.length} 次</span>`);
  }
  if (q.note) {
    dataChips.push(`<span class="q-data-chip" title="有笔记">✎ ${q.note.length} 字</span>`);
  }

  // Lesson 来源面包屑（仅当 q 来自 curriculum drill 时显示）— graceful: 没有 lesson 信息就不渲染
  let breadcrumbHTML = '';
  if (q.lesson_slug) {
    const concept = meStore.state.conceptsBySlug[q.lesson_slug];
    if (concept) {
      const tree = curriculumStore.state.tree;
      const trackName = (curriculumStore.state.tracks || []).find(t => t.slug === concept.track_slug)?.name || concept.track_slug || '';
      // 找到 module name
      let modName = concept.module_slug || '';
      for (const t of (curriculumStore.state.tracks || [])) {
        if (t.slug !== concept.track_slug) continue;
      }
      // 简化 — 用 concept.module_slug 作显示
      const url = getCurriculumUrl(q.lesson_slug);
      breadcrumbHTML = `
        <a class="q-lesson-bc" href="${url}" title="跳回这节课的教材">
          ← ${escapeHtml(trackName)} · ${escapeHtml(concept.name)}
        </a>
      `;
    }
  }

  return html`
    <div class="q-item">
      <div class="q-row">
        <div class="q-rating ${ratingCls}">
          <span class="sym">${ratingSym}</span>
          ${q.review_count || 0}×
        </div>
        <div class="q-body">
          ${raw(breadcrumbHTML)}
          <div class="q-text" data-practice-one="${escapeAttr(q.id)}" style="cursor:pointer" title="点击进入单题练习">${q.text}</div>
          <div class="q-meta">
            ${raw((q.topics || []).map(t => `<span class="topic">${t}</span>`).join(''))}
            ${q.next_review_at ? raw(`<span>· next ${new Date(q.next_review_at).toLocaleDateString()}</span>`) : ''}
          </div>
          ${dataChips.length > 0 ? raw(`<div class="q-data">${dataChips.join('')}</div>`) : ''}
        </div>
        <div class="q-acts">
          <button class="rate-btn" data-r="bad"  data-rate="${escapeAttr(q.id)}|bad">不会</button>
          <button class="rate-btn" data-r="ok"   data-rate="${escapeAttr(q.id)}|ok">一般</button>
          <button class="rate-btn" data-r="good" data-rate="${escapeAttr(q.id)}|good">熟练</button>
          <button class="rate-btn" data-edit-q="${escapeAttr(q.id)}" title="编辑">✎</button>
          <button class="rate-btn" data-del-q="${escapeAttr(q.id)}" title="删除">✕</button>
        </div>
      </div>
    </div>
  `;
}

function openAddQuestionModal() {
  openModal({
    title: '新增题目',
    sub: '新建一道练习题',
    body: `
      <div class="field">
        <label>题干</label>
        <textarea id="q-text" placeholder="例：解释 K8s scheduler 的扩展点和 framework"></textarea>
      </div>
      <div class="field">
        <label style="display:flex;align-items:center;gap:10px">
          技能点 (逗号分隔)
          <button class="btn ghost" id="q-classify" style="font-size:9px;padding:3px 8px;margin-left:auto" type="button">✦ 自动分类</button>
        </label>
        <input id="q-topics" type="text" placeholder="k8s, scheduler, golang">
      </div>
      <div id="q-classify-status" class="mono" style="font-size:9px;color:var(--char-soft);min-height:12px;letter-spacing:0.04em"></div>
    `,
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="q-save">添加</button>
    `,
    onMount(card) {
      card.querySelector('#q-save').addEventListener('click', async () => {
        const text = card.querySelector('#q-text').value.trim();
        if (!text) return;
        const topics = card.querySelector('#q-topics').value
          .split(',').map(s => s.trim()).filter(Boolean);
        try {
          await createQuestion({ text, topics });
          toast('已添加', 'success');
          closeModal();
          router.refresh();
        } catch (e) { toast(e.message, 'danger'); }
      });

      const runClassify = async (useAI = false) => {
        const text = card.querySelector('#q-text').value.trim();
        const status = card.querySelector('#q-classify-status');
        if (!text) {
          status.innerHTML = '<span style="color:var(--rust)">先填题干</span>';
          return;
        }
        const existing = card.querySelector('#q-topics').value
          .split(',').map(s => s.trim()).filter(Boolean);

        // 1. 优先本地关键词匹配（瞬间）
        const local = extractTopicsLocal(text);

        if (local.length > 0 && !useAI) {
          const merged = [...new Set([...existing, ...local])];
          card.querySelector('#q-topics').value = merged.join(', ');
          status.innerHTML = `<span style="color:var(--sage)">✓ 本地匹配到 ${local.length} 个 topic</span> · <a id="q-classify-ai" style="cursor:pointer;color:var(--char-soft);text-decoration:underline">让 AI 再增强一下</a>`;
          card.querySelector('#q-classify-ai')?.addEventListener('click', () => runClassify(true));
          return;
        }

        // 2. 本地没匹配到 OR 显式 AI → 调 LLM
        const btn = card.querySelector('#q-classify');
        btn.disabled = true;
        status.textContent = useAI ? '⋯ AI 增强中' : '⋯ 本地无匹配，让 AI 兜底';
        try {
          const r = await questionsApi.classify(text);
          const merged = [...new Set([...existing, ...local, ...(r.topics || [])])];
          card.querySelector('#q-topics').value = merged.join(', ');
          status.innerHTML = `<span style="color:var(--sage)">✓ 共 ${merged.length - existing.length} 个 topic（本地 ${local.length} + AI ${r.topics?.length || 0}）</span>`;
        } catch (e) {
          if (local.length > 0) {
            const merged = [...new Set([...existing, ...local])];
            card.querySelector('#q-topics').value = merged.join(', ');
            status.innerHTML = `<span style="color:var(--amber-soft)">AI 失败但本地匹配到 ${local.length} 个</span>`;
          } else {
            status.innerHTML = `<span style="color:var(--rust)">✕ ${e.message}</span>`;
          }
        } finally {
          btn.disabled = false;
        }
      };
      card.querySelector('#q-classify').addEventListener('click', () => runClassify(false));
    },
  });
}

// ─── AI 出题 modal ───
function openAIGenerateModal() {
  // 默认 topic 用当前 sidebar 选中的
  const defaultTopic = topicFilter || '';
  openModal({
    title: '✦ AI 出题',
    sub: '生成的题目可以预览后再批量入库',
    body: `
      <style>
        .gen-form { display: flex; flex-direction: column; gap: 12px; }
        .gen-form .row { display: flex; gap: 12px; }
        .gen-form .row .field { flex: 1; }
        .gen-result {
          margin-top: 16px;
          padding: 14px;
          background: rgba(196, 123, 42, 0.05);
          border: 1px solid var(--line-paper-2);
          border-left: 2px solid var(--amber);
          font-family: var(--font-serif);
          font-size: 14px;
          line-height: 1.6;
          white-space: pre-wrap;
          min-height: 80px;
          max-height: 360px;
          overflow-y: auto;
        }
        .gen-list { margin-top: 14px; }
        .gen-q-row {
          display: flex;
          gap: 10px;
          padding: 8px 10px;
          margin-bottom: 4px;
          border: 1px solid var(--line-paper-2);
          font-family: var(--font-serif);
          font-size: 13px;
          color: var(--char);
          align-items: baseline;
        }
        .gen-q-row input[type=checkbox] { width: auto; margin-top: 3px; flex-shrink: 0; }
        .gen-q-row label { cursor: pointer; flex: 1; }
      </style>
      <div class="gen-form">
        <div class="field">
          <label>Topic / 主题</label>
          <input id="gen-topic" type="text" value="${escapeHtml(defaultTopic)}" placeholder="例：k8s scheduler / golang gc / 分布式锁">
        </div>
        <div class="row">
          <div class="field">
            <label>数量</label>
            <input id="gen-count" type="number" value="5" min="1" max="20">
          </div>
          <div class="field">
            <label>难度</label>
            <select id="gen-diff">
              <option value="easy">入门</option>
              <option value="medium" selected>中等</option>
              <option value="hard">深挖</option>
            </select>
          </div>
          <div class="field">
            <label>风格</label>
            <select id="gen-style">
              <option>技术原理</option>
              <option>项目深挖</option>
              <option>系统设计</option>
              <option>Trade-off</option>
            </select>
          </div>
        </div>
        <div id="gen-status" class="mono" style="font-size:10px;color:var(--char-soft);min-height:14px"></div>
      </div>
      <div id="gen-result-host"></div>
    `,
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn" id="gen-go">▶ 生成</button>
      <button class="btn primary" id="gen-import" style="display:none">⤓ 入库选中的题</button>
    `,
    onMount(card) {
      let parsedQs = [];
      let activeAbort = null;

      const goBtn = card.querySelector('#gen-go');
      const importBtn = card.querySelector('#gen-import');
      const status = card.querySelector('#gen-status');
      const host = card.querySelector('#gen-result-host');

      goBtn.addEventListener('click', async () => {
        const topic = card.querySelector('#gen-topic').value.trim();
        if (!topic) { toast('请填 topic', 'danger'); return; }
        const count = parseInt(card.querySelector('#gen-count').value, 10) || 5;
        const difficulty = card.querySelector('#gen-diff').value;
        const style = card.querySelector('#gen-style').value;

        // 收集已有题目避免重复
        const avoid = (questionsStore.state.questions || [])
          .filter(q => (q.topics || []).some(t => t.toLowerCase().includes(topic.toLowerCase()) || topic.toLowerCase().includes(t.toLowerCase())))
          .map(q => q.text);

        host.innerHTML = `<div class="gen-result" id="gen-stream"></div>`;
        const liveEl = host.querySelector('#gen-stream');
        const startTs = Date.now();
        status.textContent = '⋯ 生成中 0s';
        const timer = setInterval(() => {
          status.textContent = `⋯ 生成中 ${Math.floor((Date.now() - startTs) / 1000)}s`;
        }, 500);
        goBtn.disabled = true;

        try {
          const handle = questionsApi.generateStream(
            { topic, count, difficulty, style, avoid },
            {
              onDelta: (_, full) => { liveEl.textContent = full; },
            }
          );
          activeAbort = handle.abort;
          const full = await handle.promise;
          clearInterval(timer);

          // 解析行：以 Q1: Q2: ... 开头的
          parsedQs = [];
          for (const line of full.split('\n')) {
            const m = line.match(/^Q\d+[\.\:、]\s*(.+)$/);
            if (m) parsedQs.push(m[1].trim());
          }

          if (parsedQs.length === 0) {
            // fallback：按非空行
            parsedQs = full.split('\n').map(l => l.trim()).filter(l => l && l.length > 8);
          }

          status.textContent = `✓ 解析出 ${parsedQs.length} 道题`;
          // 渲染可选清单
          host.innerHTML = `
            <div class="gen-list">
              <div class="mono" style="font-size:10px;color:var(--char-soft);margin-bottom:8px;letter-spacing:0.08em;text-transform:uppercase">◇ 选择要入库的题目</div>
              ${parsedQs.map((q, i) => `
                <div class="gen-q-row">
                  <input type="checkbox" id="gen-pick-${i}" data-pick="${i}" checked>
                  <label for="gen-pick-${i}">${escapeHtml(q)}</label>
                </div>
              `).join('')}
            </div>
          `;
          importBtn.style.display = 'inline-flex';
          goBtn.textContent = '↻ 重新生成';
          goBtn.disabled = false;
        } catch (e) {
          clearInterval(timer);
          status.textContent = '✕ ' + e.message;
          goBtn.disabled = false;
        }
      });

      importBtn.addEventListener('click', async () => {
        const picks = [...card.querySelectorAll('[data-pick]:checked')].map(el => parsedQs[parseInt(el.dataset.pick, 10)]).filter(Boolean);
        if (picks.length === 0) { toast('一道都没选', 'danger'); return; }
        const topic = card.querySelector('#gen-topic').value.trim();
        const baseTopics = topic.split(/[,，\s]+/).filter(Boolean);

        importBtn.disabled = true;
        importBtn.textContent = '⋯ 入库中';
        try {
          // 本地关键词匹配 — 0 调用 LLM，瞬间完成
          for (const text of picks) {
            const local = extractTopicsLocal(text);
            const merged = [...new Set([...baseTopics, ...local])];
            await questionsApi.create({ text, topics: merged, source: 'ai_generated' });
          }
          await loadQuestions();
          toast(`已导入 ${picks.length} 道题（本地自动分类）`, 'success');
          closeModal();
          router.refresh();
        } catch (e) {
          toast('导入失败：' + e.message, 'danger');
        } finally {
          importBtn.disabled = false;
          importBtn.textContent = '⤓ 入库选中的题';
        }
      });
    },
  });
}

function openEditQuestionModal(q) {
  const topicsStr = (q.topics || []).join(', ');
  const variants = Array.isArray(q.answer_variants) ? q.answer_variants : [];
  const analyses = Array.isArray(q.analyses) ? q.analyses : [];
  const sessions = Array.isArray(q.chat_sessions) ? q.chat_sessions : [];
  const SOURCES = [
    { v: 'manual', label: '手动' },
    { v: 'interview', label: '面试' },
    { v: 'derived', label: '衍生' },
    { v: 'ai_generated', label: 'AI 生成' },
  ];
  const ratingZh = { good: '熟练', ok: '一般', bad: '不会' };
  openModal({
    title: '编辑题目',
    sub: q.id,
    body: `
      <div class="field">
        <label>题干</label>
        <textarea id="qe-text" rows="4">${escapeHtml(q.text)}</textarea>
      </div>
      <div class="field">
        <label style="display:flex;align-items:center;gap:10px">
          技能点 (逗号分隔)
          <button class="btn ghost" id="qe-classify" type="button" style="font-size:9px;padding:3px 8px;margin-left:auto">✦ 自动分类</button>
        </label>
        <input id="qe-topics" type="text" value="${escapeHtml(topicsStr)}">
      </div>
      <div id="qe-classify-status" class="mono" style="font-size:9px;color:var(--char-soft);min-height:12px;letter-spacing:0.04em"></div>
      <div class="field">
        <label>来源</label>
        <select id="qe-source">
          ${SOURCES.map(s => `<option value="${s.v}" ${(q.source || 'manual') === s.v ? 'selected' : ''}>${s.label}</option>`).join('')}
        </select>
      </div>
      <div class="field">
        <label>笔记</label>
        <textarea id="qe-note" rows="3">${escapeHtml(q.note || '')}</textarea>
      </div>

      <div style="margin-top:18px;padding-top:14px;border-top:1px dashed var(--line-paper-2)">
        <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ 数据 / 复习状态</div>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;font-family:var(--font-mono);font-size:11px;color:var(--char-soft)">
          <div>答案模板：<strong style="color:var(--char)">${variants.length}</strong></div>
          <div>评估次数：<strong style="color:var(--char)">${analyses.length}</strong></div>
          <div>追问会话：<strong style="color:var(--char)">${sessions.length}</strong></div>
          <div>复习次数：<strong style="color:var(--char)">${q.review_count || 0}</strong></div>
          <div>当前评分：<strong style="color:var(--char)">${ratingZh[q.rating] || '未评'}</strong></div>
          <div>下次复习：<strong style="color:var(--char)">${q.next_review_at ? new Date(q.next_review_at).toLocaleDateString('zh-CN') : '—'}</strong></div>
        </div>
        <button class="btn ghost" id="qe-reset-review" type="button" style="font-size:10px;padding:5px 12px;margin-top:10px">↻ 重置复习状态</button>
      </div>
    `,
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="qe-save">保存</button>
    `,
    onMount(card) {
      card.querySelector('#qe-save').addEventListener('click', async () => {
        const text = card.querySelector('#qe-text').value.trim();
        if (!text) return;
        const topics = card.querySelector('#qe-topics').value
          .split(',').map(s => s.trim()).filter(Boolean);
        const note = card.querySelector('#qe-note').value;
        const source = card.querySelector('#qe-source').value;
        try {
          await questionsApi.patch(q.id, { text, topics, note, source });
          await loadQuestions();
          toast('已保存', 'success');
          closeModal();
          router.refresh();
        } catch (e) { toast(e.message, 'danger'); }
      });

      card.querySelector('#qe-reset-review').addEventListener('click', async () => {
        // 快照原值用于撤销
        const snapshot = {
          rating: q.rating,
          review_count: q.review_count,
          last_reviewed_at: q.last_reviewed_at,
          next_review_at: q.next_review_at,
        };
        try {
          await questionsApi.patch(q.id, {
            rating: null,
            review_count: 0,
            last_reviewed_at: null,
            next_review_at: null,
          });
          await loadQuestions();
          toast('已重置复习状态', 'success');
          closeModal();
          router.refresh();
          undoableToast('复习状态已重置', async () => {
            await questionsApi.patch(q.id, snapshot);
            await loadQuestions();
            router.refresh();
            toast('已恢复', 'success');
          }, { kind: 'success' });
        } catch (e) { toast(e.message, 'danger'); }
      });

      const runEditClassify = async (useAI = false) => {
        const text = card.querySelector('#qe-text').value.trim();
        const status = card.querySelector('#qe-classify-status');
        if (!text) {
          status.innerHTML = '<span style="color:var(--rust)">题干为空</span>';
          return;
        }
        const existing = card.querySelector('#qe-topics').value
          .split(',').map(s => s.trim()).filter(Boolean);

        const local = extractTopicsLocal(text);
        if (local.length > 0 && !useAI) {
          const merged = [...new Set([...existing, ...local])];
          card.querySelector('#qe-topics').value = merged.join(', ');
          status.innerHTML = `<span style="color:var(--sage)">✓ 本地匹配到 ${local.length} 个 topic</span> · <a id="qe-classify-ai" style="cursor:pointer;color:var(--char-soft);text-decoration:underline">让 AI 再增强一下</a>`;
          card.querySelector('#qe-classify-ai')?.addEventListener('click', () => runEditClassify(true));
          return;
        }

        const btn = card.querySelector('#qe-classify');
        btn.disabled = true;
        status.textContent = useAI ? '⋯ AI 增强中' : '⋯ 本地无匹配，让 AI 兜底';
        try {
          const r = await questionsApi.classify(text);
          const merged = [...new Set([...existing, ...local, ...(r.topics || [])])];
          card.querySelector('#qe-topics').value = merged.join(', ');
          status.innerHTML = `<span style="color:var(--sage)">✓ 共新增 ${merged.length - existing.length} 个 topic</span>`;
        } catch (e) {
          if (local.length > 0) {
            const merged = [...new Set([...existing, ...local])];
            card.querySelector('#qe-topics').value = merged.join(', ');
            status.innerHTML = `<span style="color:var(--amber-soft)">AI 失败但本地匹配 ${local.length} 个</span>`;
          } else {
            status.innerHTML = `<span style="color:var(--rust)">✕ ${e.message}</span>`;
          }
        } finally {
          btn.disabled = false;
        }
      };
      card.querySelector('#qe-classify').addEventListener('click', () => runEditClassify(false));
    },
  });
}
