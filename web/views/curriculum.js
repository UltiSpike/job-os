// Curriculum view — Layout A++
//
// 三段式：track header / module tabs / (lesson list | lesson detail)
// CSS grid 写成 220px / 1fr，将来加 module 列变三栏只改一行
//
// 状态持久化：URL hash = #/curriculum/<track>/<module>/<lesson>
// 通过 history.replaceState 写入，避免 hashchange 触发额外 refresh
//
// drill / capstone 都是 questions 表里的行 → 点击 → 复用 _practiceModal
// 毕业题"通过"由后端 hook 维护：在 capstone 上创建 analysis(score>=70) → 自动 upsert lesson_progress

import { html, raw } from '../components/html.js';
import { curriculumStore, loadCurriculum, reloadTree, switchTrack } from '../store/curriculum.js';
import { curriculumApi } from '../api/curriculum.js';
import { questionsApi } from '../api/questions.js';
import { analysesApi } from '../api/analyses.js';
import { openPractice } from './_practiceModal.js';
import { toast } from '../components/toast.js';
import { meStore, refreshMastery, getMasteryForLesson } from '../store/me.js';
import { masteryDeltaToast } from '../components/rewardToast.js';

// ─── 视图状态 ───
let activeModuleSlug = null;     // 当前展开的 module
let selectedLessonSlug = null;   // 右栏正在看的 lesson
let selectedSectionKey = null;   // null = section 列表, 'why'/'core'/... = section 详情
let drillCache = {};             // lessonSlug → [drill question rows]
let capstoneCache = {};          // lessonSlug → capstone question row
let capstoneAnalysisCache = {};  // lessonSlug → latest analysis (or null)

// ─── URL hash 持久化 ───
function readHashState() {
  const segs = location.hash.replace('#/', '').split('/');
  // [view, track, module, lesson, section]
  return {
    track: segs[1] || null,
    module: segs[2] || null,
    lesson: segs[3] || null,
    section: segs[4] || null,
  };
}

function writeHashState() {
  const tree = curriculumStore.state.tree;
  const trackSlug = tree?.slug || curriculumStore.state.activeTrackSlug || '';
  const parts = ['curriculum'];
  if (trackSlug) parts.push(trackSlug);
  if (activeModuleSlug) parts.push(activeModuleSlug);
  if (selectedLessonSlug) parts.push(selectedLessonSlug);
  if (selectedSectionKey) parts.push(selectedSectionKey);
  const newHash = '#/' + parts.join('/');
  if (location.hash !== newHash) {
    history.replaceState({}, '', newHash);
  }
}

// ─── 数据加载 ───
async function loadLessonQuestions(lessonSlug) {
  if (!lessonSlug) return;
  if (drillCache[lessonSlug] && capstoneCache[lessonSlug]) return;
  try {
    const [drillsRes, capQ] = await Promise.all([
      curriculumApi.listDrills(lessonSlug),
      curriculumApi.ensureCapstoneQuestion(lessonSlug),
    ]);
    drillCache[lessonSlug] = drillsRes.items || [];
    capstoneCache[lessonSlug] = capQ;
    // 拉一次最近的 analysis 用于"上次评估"展示
    if (capQ?.id) {
      try {
        const an = await analysesApi.listForQuestion(capQ.id);
        const items = an.items || [];
        capstoneAnalysisCache[lessonSlug] = items.length
          ? items.sort((a, b) => (b.at || '').localeCompare(a.at || ''))[0]
          : null;
      } catch (_) { capstoneAnalysisCache[lessonSlug] = null; }
    }
    rerender();
  } catch (e) {
    toast('载入题目失败：' + e.message, 'danger');
  }
}

async function openLessonPractice(lessonSlug, startQid) {
  try {
    const drills = drillCache[lessonSlug] || [];
    const cap = capstoneCache[lessonSlug];
    const ids = [...drills.map(d => d.id), cap?.id].filter(Boolean);
    const queue = await Promise.all(ids.map(id => questionsApi.get(id)));
    const startIdx = Math.max(0, queue.findIndex(q => q.id === startQid));
    // 记录 before mastery
    const beforeMastery = getMasteryForLesson(lessonSlug);
    await openPractice(queue, startIdx);
    // 模态关闭后刷新 + 触发 reward toast
    setTimeout(async () => {
      try {
        await Promise.all([reloadTree(), refreshMastery()]);
        if (cap?.id) {
          const an = await analysesApi.listForQuestion(cap.id);
          const items = an.items || [];
          capstoneAnalysisCache[lessonSlug] = items.length
            ? items.sort((a, b) => (b.at || '').localeCompare(a.at || ''))[0]
            : null;
        }
        // 弹 reward toast
        const afterMastery = getMasteryForLesson(lessonSlug);
        const lesson = findLesson(lessonSlug);
        if (lesson && afterMastery) {
          masteryDeltaToast(beforeMastery, afterMastery, lesson.name);
        }
        rerender();
      } catch (_) {}
    }, 300);
  } catch (e) {
    toast('打开练习失败：' + e.message, 'danger');
  }
}

// ─── helpers ───
function statusGlyph(progress, prereqOk) {
  const s = progress?.status;
  if (s === 'passed') return { ch: '✓', cls: 'st-passed' };
  if (s === 'in_progress') return { ch: '●', cls: 'st-progress' };
  if (!prereqOk) return { ch: '╳', cls: 'st-locked' };
  return { ch: '○', cls: 'st-available' };
}

function isPrereqSatisfied(lesson, progressMap) {
  for (const slug of (lesson.prereq_slugs || [])) {
    if ((progressMap[slug]?.status) !== 'passed') return false;
  }
  return true;
}

function progressMapFromTree(tree) {
  const m = {};
  if (!tree) return m;
  for (const mod of tree.modules) for (const l of mod.lessons) {
    if (l.progress) m[l.slug] = l.progress;
  }
  return m;
}

function pickInitialModule(tree) {
  if (!tree || !tree.modules.length) return null;
  for (const m of tree.modules) {
    if (m.lessons.some(l => l.progress?.status === 'in_progress')) return m.slug;
  }
  for (const m of tree.modules) {
    if (m.lessons.some(l => l.progress?.status !== 'passed')) return m.slug;
  }
  return tree.modules[0].slug;
}

function pickInitialLesson(mod) {
  if (!mod || !mod.lessons.length) return null;
  // 优先 in_progress
  const inProg = mod.lessons.find(l => l.progress?.status === 'in_progress');
  if (inProg) return inProg.slug;
  // 然后第一个未通过
  const next = mod.lessons.find(l => l.progress?.status !== 'passed');
  if (next) return next.slug;
  // 全通过：选第一节
  return mod.lessons[0].slug;
}

function findLesson(slug, tree = curriculumStore.state.tree) {
  if (!tree) return null;
  for (const m of tree.modules) for (const l of m.lessons) if (l.slug === slug) return l;
  return null;
}

function findModule(slug, tree = curriculumStore.state.tree) {
  if (!tree) return null;
  return tree.modules.find(m => m.slug === slug) || null;
}

function rerender() {
  import('../app.js').then(({ router }) => router.refresh());
}

// ─── markdown 渲染 ───
function escMd(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
          .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function inlineMd(t) {
  return escMd(t).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
                 .replace(/`([^`]+)`/g,'<code>$1</code>');
}
function renderSimpleTable(text) {
  const lines = text.split('\n').filter(l => l.trim().startsWith('|'));
  if (lines.length < 2) return `<p>${inlineMd(text)}</p>`;
  const parseRow = l => l.split('|').slice(1,-1).map(c => c.trim());
  const hds = parseRow(lines[0]);
  const rows = lines.slice(2); // skip separator
  let t = '<table><thead><tr>' + hds.map(h => `<th>${inlineMd(h)}</th>`).join('') + '</tr></thead><tbody>';
  rows.forEach(r => { t += '<tr>' + parseRow(r).map(c => `<td>${inlineMd(c)}</td>`).join('') + '</tr>'; });
  return t + '</tbody></table>';
}

// 按 fenced code block 边界 + 空行切成顶层 block 列表。
// 代码块保留为独立 block，里面的空行不会被二次拆分。
function splitMdBlocks(md) {
  if (!md) return [];
  const lines = String(md).split('\n');
  const blocks = [];
  let buf = [];
  let inFence = false;
  let fenceLang = '';
  let fenceLines = [];
  const flushText = () => {
    const text = buf.join('\n').replace(/^\n+|\n+$/g, '');
    if (text) blocks.push({ type: 'text', content: text });
    buf = [];
  };
  for (const line of lines) {
    const fenceOpen = line.match(/^\s*```\s*([\w.+-]*)\s*$/);
    if (fenceOpen) {
      if (inFence) {
        blocks.push({ type: 'code', lang: fenceLang, content: fenceLines.join('\n') });
        fenceLines = [];
        fenceLang = '';
        inFence = false;
      } else {
        flushText();
        inFence = true;
        fenceLang = fenceOpen[1] || '';
      }
      continue;
    }
    if (inFence) {
      fenceLines.push(line);
    } else if (line.trim() === '') {
      flushText();
    } else {
      buf.push(line);
    }
  }
  if (inFence) {
    // 未闭合 fence：保底当作代码块
    blocks.push({ type: 'code', lang: fenceLang, content: fenceLines.join('\n') });
  }
  flushText();
  return blocks;
}

function renderBlock(b) {
  if (b.type === 'code') {
    const label = b.lang ? `<span class="curr-code-lang">${escMd(b.lang)}</span>` : '';
    return `<pre class="curr-code">${label}<code>${escMd(b.content)}</code></pre>`;
  }
  const trimmed = b.content.trim();
  if (trimmed.startsWith('|')) return `<div class="curr-table-wrap">${renderSimpleTable(trimmed)}</div>`;
  if (/^- /.test(trimmed)) {
    const items = trimmed.split('\n').filter(l => l.trim().startsWith('- '))
      .map(l => `<li>${inlineMd(l.replace(/^-\s*/,''))}</li>`).join('');
    return `<ul>${items}</ul>`;
  }
  return `<p>${inlineMd(trimmed)}</p>`;
}

function renderMd(md) {
  return splitMdBlocks(md).map(renderBlock).join('');
}
function renderConcept(md) { return raw(renderMd(md)); }

// ─── section inline 渲染（lesson 主页，TOC scroll + 全部 sections 展示）───
function renderSectionsInline(lesson) {
  const sections = lesson.sections || [];
  const mm = lesson.mental_model || '';
  if (!sections.length) {
    return html`<section class="curr-concept">${renderConcept(lesson.concept_md)}</section>`;
  }
  return html`
    <nav class="curr-toc">
      ${sections.map((s, i) => html`
        <a class="curr-toc-item" data-scroll-sect="${s.key}">
          <span class="toc-num">${String(i+1).padStart(2,'0')}</span>
          ${s.title}
        </a>
      `)}
    </nav>
    <div class="curr-sections">
      ${sections.map((s, i) => html`
        <section class="curr-section" id="sect-${s.key}">
          <h4 class="curr-section-title">
            <span class="sect-num">${String(i+1).padStart(2,'0')}</span>
            ${s.title}
          </h4>
          <div class="curr-section-body">${raw(renderMd(s.content_md))}</div>
        </section>
      `)}
      ${mm ? html`
        <aside class="curr-mental-model">
          <span class="mm-icon">◈</span>
          <div class="mm-text">${raw(renderMd(mm))}</div>
        </aside>
      ` : ''}
    </div>
  `;
}

// ─── 子标题解析（从 content_md 提取 **N. Title** 模式）───
const SUB_HEADING_RE = /^\*\*(?:(\d+)\.\s*)?(.+?)\*\*$/;
function parseSubHeadings(md) {
  const blocks = splitMdBlocks(md);
  const subs = []; // { id, title, num, blockIdx }
  blocks.forEach((b, i) => {
    if (b.type !== 'text') return;
    const firstLine = b.content.trim().split('\n')[0];
    const m = firstLine.match(SUB_HEADING_RE);
    if (m) {
      const num = m[1] || String(subs.length + 1);
      const title = m[2].trim();
      subs.push({ id: `sub-${num}`, title, num, blockIdx: i });
    }
  });
  return subs;
}

// ─── section 详情（子页面，复用 inline TOC 设计）───
function renderSectionDetail(lesson) {
  const sections = lesson.sections || [];
  const idx = sections.findIndex(s => s.key === selectedSectionKey);
  if (idx < 0) return html`<div class="curr-detail-empty">未找到该 section</div>`;
  const sect = sections[idx];
  const prevSect = idx > 0 ? sections[idx - 1] : null;
  const nextSect = idx < sections.length - 1 ? sections[idx + 1] : null;
  const subs = parseSubHeadings(sect.content_md);
  const hasSubs = subs.length >= 2;

  // 渲染 content_md，给子标题段落加 id 锚点
  function renderWithAnchors(md) {
    const blocks = splitMdBlocks(md);
    let subIdx = 0;
    return blocks.map(b => {
      if (b.type === 'text') {
        const firstLine = b.content.trim().split('\n')[0];
        const m = firstLine.match(SUB_HEADING_RE);
        if (m && subIdx < subs.length) {
          const sub = subs[subIdx++];
          return `<div id="${sub.id}" class="curr-sub-anchor">${renderBlock(b)}</div>`;
        }
      }
      return renderBlock(b);
    }).join('');
  }

  return html`
    <article class="curr-section-detail">
      <nav class="curr-section-breadcrumb" data-section-back>
        <span class="breadcrumb-arrow">←</span>
        <span class="breadcrumb-lesson">${lesson.name}</span>
      </nav>
      <header class="curr-section-head">
        <span class="section-head-num">${String(idx+1).padStart(2,'0')} / ${String(sections.length).padStart(2,'0')}</span>
        <h3>${sect.title}</h3>
      </header>
      ${hasSubs ? html`
        <nav class="curr-toc curr-sub-toc">
          ${subs.map(s => html`
            <a class="curr-toc-item" data-scroll-sub="${s.id}">
              <span class="toc-num">${s.num}</span>
              ${s.title}
            </a>
          `)}
        </nav>
      ` : ''}
      <div class="curr-section-content">${raw(hasSubs ? renderWithAnchors(sect.content_md) : renderMd(sect.content_md))}</div>
      <nav class="curr-section-nav">
        ${prevSect
          ? html`<button class="btn ghost sect-prev" data-section-go="${prevSect.key}">← ${prevSect.title}</button>`
          : html`<span></span>`}
        ${nextSect
          ? html`<button class="btn ghost sect-next" data-section-go="${nextSect.key}">${nextSect.title} →</button>`
          : html`<button class="btn ghost sect-back-end" data-section-back>回到概览</button>`}
      </nav>
    </article>
  `;
}

// ─── 渲染：track header ───
function renderTrackHeader(tree) {
  const passed = Object.values(progressMapFromTree(tree)).filter(p => p.status === 'passed').length;
  const total = tree.modules.reduce((s, m) => s + m.lessons.length, 0);
  const tracks = curriculumStore.state.tracks || [];
  const multi = tracks.length > 1;
  return html`
    <div class="curr-trackbar">
      ${multi ? html`
        <div class="curr-trackswitch">
          ${tracks.map(t => html`
            <button class="curr-trackbtn ${t.slug === tree.slug ? 'active' : ''}" data-track="${t.slug}">
              ${t.name}
            </button>
          `)}
        </div>
      ` : html`<div class="curr-trackname">${tree.name}</div>`}
      <div class="curr-trackprog">${passed} / ${total}</div>
    </div>
  `;
}

// ─── 渲染：module tabs ───
function renderModuleTabs(tree) {
  const progressMap = progressMapFromTree(tree);
  return html`
    <div class="curr-modtabs">
      ${tree.modules.map(m => {
        const passedN = m.lessons.filter(l => progressMap[l.slug]?.status === 'passed').length;
        const totalN = m.lessons.length;
        const pct = totalN ? Math.round((passedN / totalN) * 100) : 0;
        const active = m.slug === activeModuleSlug;
        return html`
          <button class="curr-modtab ${active ? 'active' : ''}" data-mod="${m.slug}" style="--prog:${pct}%">
            <span class="modtab-name">${m.name}</span>
            <span class="modtab-num">${passedN}/${totalN}</span>
          </button>
        `;
      })}
    </div>
  `;
}

// ─── 渲染：lesson list（当前 module）───
function renderLessonList(tree) {
  const mod = findModule(activeModuleSlug, tree);
  if (!mod) return html`<div class="curr-lesslist-empty">选一个 module</div>`;
  const progressMap = progressMapFromTree(tree);
  return html`
    <ul class="curr-lesslist">
      ${mod.lessons.map(l => {
        const ok = isPrereqSatisfied(l, progressMap);
        const m = getMasteryForLesson(l.slug);
        let g;
        if (m && m.status === 'mastered') g = { ch: '✓', cls: 'st-passed' };
        else if (m && m.status === 'rusty') g = { ch: '⟳', cls: 'st-rusty' };
        else if (m && m.status === 'learning') g = { ch: '●', cls: 'st-progress' };
        else if (!ok) g = { ch: '╳', cls: 'st-locked' };
        else g = { ch: '○', cls: 'st-available' };
        const isSelected = selectedLessonSlug === l.slug;
        const sel = isSelected ? 'sel' : '';
        const masteryPct = m ? Math.round((m.score || 0) * 100) : null;
        const sections = (l.sections || []);
        const expanded = isSelected && sections.length > 0;
        return html`
          <li class="curr-lessrow ${sel}" data-lesson="${l.slug}" style="--m:${masteryPct ?? 0}%">
            <span class="lessrow-glyph ${g.cls}">${expanded ? '▾' : g.ch}</span>
            <span class="lessrow-num">${String(l.order_index).padStart(2, '0')}</span>
            <span class="lessrow-name">${l.name}</span>
            <span class="lessrow-est">${masteryPct != null ? masteryPct + '%' : l.est_minutes + 'm'}</span>
          </li>
          ${expanded ? html`
            <li class="curr-seclist-wrap">
              <ul class="curr-seclist">
                ${sections.map((s, i) => {
                  const active = selectedSectionKey === s.key ? 'active' : '';
                  return html`
                    <li class="curr-secitem ${active}" data-section-go="${s.key}">
                      <span class="secitem-num">${String(i+1).padStart(2,'0')}</span>
                      <span class="secitem-title">${s.title}</span>
                    </li>
                  `;
                })}
              </ul>
            </li>
          ` : ''}
        `;
      })}
    </ul>
  `;
}

// ─── 渲染：lesson detail ───
function renderLessonDetail() {
  if (!selectedLessonSlug) {
    return html`<div class="curr-detail-empty">← 选一节课</div>`;
  }
  const lesson = findLesson(selectedLessonSlug);
  if (!lesson) return html`<div class="curr-detail-empty">未找到这节课</div>`;

  // Section 详情模式
  if (selectedSectionKey && (lesson.sections || []).length) {
    return renderSectionDetail(lesson);
  }

  // Section 列表模式（lesson 概览页）
  const drills = drillCache[selectedLessonSlug];
  const cap = capstoneCache[selectedLessonSlug];
  const lastAn = capstoneAnalysisCache[selectedLessonSlug];
  const progress = lesson.progress;
  const mastery = getMasteryForLesson(selectedLessonSlug);

  let statusLabel;
  if (mastery && mastery.status === 'mastered') statusLabel = '已掌握';
  else if (mastery && mastery.status === 'rusty') statusLabel = '需要复习';
  else if (mastery && mastery.status === 'learning') statusLabel = '学习中';
  else if (progress?.status === 'passed') statusLabel = '已通过';
  else if (progress?.status === 'in_progress') statusLabel = '进行中';
  else statusLabel = '未开始';
  const masteryPct = mastery ? Math.round((mastery.score || 0) * 100) : null;

  return html`
    <article class="curr-detail">
      <header class="curr-detail-head">
        <h3>${lesson.name}</h3>
        <div class="curr-detail-meta">
          ${lesson.est_minutes} min · ${statusLabel}
          ${masteryPct != null ? raw(`<span class="curr-mastery-inline">掌握度 ${masteryPct}%</span>`) : ''}
        </div>
      </header>

      ${renderSectionsInline(lesson)}

      <section class="curr-drills-section">
        <h4>◇ 练手题（${drills ? drills.length : '…'}）</h4>
        ${drills === undefined ? html`<div class="curr-drills-empty">载入中…</div>` :
          drills.length === 0 ? html`<div class="curr-drills-empty">这节课暂时没配练手题</div>` :
          html`<div class="curr-drill-list">
            ${drills.map((d, i) => {
              const ratingSym = d.rating === 'good' ? '✓' : d.rating === 'ok' ? '◐' : d.rating === 'bad' ? '○' : (d.first_seen_at ? '·' : '○');
              const ratingCls = d.rating || (d.first_seen_at ? 'touched' : 'new');
              return html`
                <div class="curr-drill" data-open-q="${d.id}">
                  <span class="curr-drill-num">Q${i+1}</span>
                  <span class="curr-drill-status r-${ratingCls}">${ratingSym}</span>
                  <span class="curr-drill-text">${d.text}</span>
                  <span class="curr-drill-go">▸</span>
                </div>
              `;
            })}
          </div>`
        }
      </section>

      <section class="curr-capstone-section">
        <h4>★ 毕业题</h4>
        <div class="curr-capstone-prompt">${lesson.capstone_prompt}</div>

        ${lastAn ? html`
          <div class="curr-capstone-last">
            <div class="cap-last-line">
              <span class="cap-last-score ${lastAn.score >= 70 ? 'high' : 'low'}">${lastAn.score ?? '—'}/100</span>
              <span class="cap-last-when">${new Date(lastAn.at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>
              <span class="cap-last-tag">${lastAn.score >= 70 ? '✓ PASSED' : '需要再练'}</span>
            </div>
            ${(lastAn.gaps || []).length ? html`
              <div class="cap-last-gaps">
                <span class="cap-gaps-label">弱项：</span>
                ${(lastAn.gaps || []).slice(0, 4).map(g => html`<span class="cap-gap-chip">${g}</span>`)}
              </div>
            ` : ''}
          </div>
        ` : ''}

        ${cap ? html`
          <div class="curr-capstone-actions">
            <button class="btn primary" data-open-q="${cap.id}">
              ${lastAn ? (lastAn.score >= 70 ? '↻ 再挑战一次' : '▶ 继续挑战') : '▶ 进入毕业题练习'}
            </button>
            ${lastAn && lastAn.score < 70 ? html`
              <button class="btn ghost" data-scroll-concept>↑ 先回顾教材</button>
            ` : ''}
          </div>
        ` : html`<div class="curr-drills-empty">载入中…</div>`}
      </section>
    </article>
  `;
}

// ─── view 主入口 ───
export const curriculumView = {
  name: 'curriculum',
  label: 'curriculum',
  badge: () => {
    const tree = curriculumStore.state.tree;
    if (!tree) return null;
    const all = tree.modules.flatMap(m => m.lessons);
    const passed = all.filter(l => l.progress?.status === 'passed').length;
    return all.length ? `${passed}/${all.length}` : null;
  },
  render() {
    const tree = curriculumStore.state.tree;
    if (!tree) {
      return html`
        <section class="view view-curriculum">
          <header class="page-head">
            <div class="page-num">005 / CURRICULUM</div>
            <h1 class="page-title">课程<span class="accent">.</span></h1>
            <p class="page-lede">载入中…</p>
          </header>
        </section>
      `;
    }
    return html`
      <section class="view view-curriculum">
        <header class="page-head">
          <div class="page-num">005 / CURRICULUM</div>
          <h1 class="page-title">课程<span class="accent">.</span></h1>
          <p class="page-lede">系统补一块知识，按 lesson 走，毕业题不通过不算过。</p>
        </header>
        ${renderTrackHeader(tree)}
        ${renderModuleTabs(tree)}
        <div class="curr-grid">
          <aside class="curr-lesslist-pane">${renderLessonList(tree)}</aside>
          <main class="curr-detail-pane">${renderLessonDetail()}</main>
        </div>
      </section>
    `;
  },
  mount(root) {
    // 第一次进 / 数据未加载：触发 store 加载，加载完再走 mount 里的初始化
    const initFromTree = () => {
      const tree = curriculumStore.state.tree;
      if (!tree) return;
      const hashState = readHashState();
      // 0. 若 URL 指定了不同的 track，先切 track（异步，切完会重新触发 init）
      if (hashState.track && hashState.track !== tree.slug) {
        const tracks = curriculumStore.state.tracks || [];
        if (tracks.find(t => t.slug === hashState.track)) {
          activeModuleSlug = null;
          selectedLessonSlug = null;
          switchTrack(hashState.track).then(() => rerender());
          return;
        }
      }
      // 1. 决定 active module
      activeModuleSlug = (hashState.module && findModule(hashState.module, tree))
        ? hashState.module
        : pickInitialModule(tree);
      // 2. 决定 selected lesson
      const restoredLesson = hashState.lesson && findLesson(hashState.lesson, tree);
      if (restoredLesson) {
        // URL 指定了 lesson — 锁定到它所属的 module
        for (const m of tree.modules) if (m.lessons.find(l => l.slug === restoredLesson.slug)) {
          activeModuleSlug = m.slug;
          break;
        }
        selectedLessonSlug = restoredLesson.slug;
        selectedSectionKey = hashState.section || null;
      } else {
        // 没指定 lesson → 自动选当前 module 的第一节该学的
        const mod = findModule(activeModuleSlug, tree);
        selectedLessonSlug = pickInitialLesson(mod);
      }
      if (selectedLessonSlug) loadLessonQuestions(selectedLessonSlug);
      writeHashState();
    };

    if (!curriculumStore.state.loaded) {
      loadCurriculum().then(() => {
        initFromTree();
        rerender();
      });
      return;
    }

    if (!activeModuleSlug) {
      initFromTree();
    }

    // ─── 事件绑定 ───
    root.querySelectorAll('[data-track]').forEach(el => {
      el.addEventListener('click', async () => {
        const slug = el.dataset.track;
        if (slug === curriculumStore.state.tree?.slug) return;
        // 切 track 时清掉所有局部缓存避免串话
        activeModuleSlug = null;
        selectedLessonSlug = null;
        selectedSectionKey = null;
        drillCache = {};
        capstoneCache = {};
        capstoneAnalysisCache = {};
        await switchTrack(slug);
        // 切完后用新 tree 自动选 module + lesson
        const tree = curriculumStore.state.tree;
        if (tree) {
          activeModuleSlug = pickInitialModule(tree);
          const mod = findModule(activeModuleSlug, tree);
          selectedLessonSlug = pickInitialLesson(mod);
          if (selectedLessonSlug) loadLessonQuestions(selectedLessonSlug);
        }
        writeHashState();
        rerender();
      });
    });

    root.querySelectorAll('[data-mod]').forEach(el => {
      el.addEventListener('click', () => {
        activeModuleSlug = el.dataset.mod;
        // 切 module 时自动选中下一节该学的 lesson —— 比空白更友好
        const tree = curriculumStore.state.tree;
        const mod = findModule(activeModuleSlug, tree);
        selectedLessonSlug = pickInitialLesson(mod);
        if (selectedLessonSlug) loadLessonQuestions(selectedLessonSlug);
        writeHashState();
        rerender();
      });
    });

    root.querySelectorAll('[data-lesson]').forEach(el => {
      el.addEventListener('click', () => {
        selectedLessonSlug = el.dataset.lesson;
        selectedSectionKey = null;
        loadLessonQuestions(selectedLessonSlug);
        writeHashState();
        rerender();
      });
    });

    root.querySelectorAll('[data-open-q]').forEach(el => {
      el.addEventListener('click', () => {
        const qid = el.dataset.openQ;
        openLessonPractice(selectedLessonSlug, qid);
      });
    });

    // sidebar section 子项：点击进入 section 子页面
    root.querySelectorAll('[data-section-go]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedSectionKey = el.dataset.sectionGo;
        writeHashState();
        rerender();
      });
    });

    // section 详情页返回
    root.querySelectorAll('[data-section-back]').forEach(el => {
      el.addEventListener('click', () => {
        selectedSectionKey = null;
        writeHashState();
        rerender();
      });
    });

    // section 子页面内的 sub-heading scroll
    root.querySelectorAll('[data-scroll-sub]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const target = root.querySelector(`#${el.dataset.scrollSub}`);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          root.querySelectorAll('.curr-sub-toc .curr-toc-item').forEach(a => a.classList.remove('active'));
          el.classList.add('active');
        }
      });
    });

    // inline TOC：scroll 到对应 section（纯阅读体验，不切子页面）
    root.querySelectorAll('[data-scroll-sect]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const target = root.querySelector(`#sect-${el.dataset.scrollSect}`);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          root.querySelectorAll('.curr-toc-item').forEach(a => a.classList.remove('active'));
          el.classList.add('active');
        }
      });
    });

    root.querySelector('[data-scroll-concept]')?.addEventListener('click', () => {
      const target = root.querySelector('.curr-sections') || root.querySelector('.curr-concept');
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  },
};
