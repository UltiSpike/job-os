// Curriculum view — track > modules > lessons + 课时详情 + 毕业题练习
import { html, raw, escapeHtml, escapeAttr } from '../components/html.js';
import { curriculumStore, loadCurriculum, reloadTree } from '../store/curriculum.js';
import { curriculumApi } from '../api/curriculum.js';
import { analysesApi } from '../api/analyses.js';
import { answersApi } from '../api/answers.js';
import { parseAnalysis } from '../lib/parseAnalysis.js';
import { toast } from '../components/toast.js';

let selectedLessonSlug = null;
let capstoneState = {
  // qid -> { question, draft, streaming, partial, parsed, lastScore, history }
};
let activeQid = null;

function statusBadge(progress) {
  const s = progress?.status || 'available';
  const map = {
    locked:      ['锁定', 'badge-locked'],
    available:   ['可学', 'badge-available'],
    in_progress: ['进行中', 'badge-progress'],
    passed:      ['已通过', 'badge-passed'],
  };
  const [label, cls] = map[s] || map.available;
  return `<span class="curr-badge ${cls}">${label}</span>`;
}

function isPrereqSatisfied(lesson, progressMap) {
  for (const slug of (lesson.prereq_slugs || [])) {
    if ((progressMap[slug]?.status) !== 'passed') return false;
  }
  return true;
}

async function startCapstone(lessonSlug) {
  try {
    const q = await curriculumApi.ensureCapstoneQuestion(lessonSlug);
    activeQid = q.id;
    if (!capstoneState[q.id]) {
      // 拉历史
      const an = await analysesApi.listForQuestion(q.id);
      capstoneState[q.id] = {
        question: q,
        draft: '',
        streaming: false,
        partial: '',
        parsed: null,
        lastScore: null,
        history: an.items || [],
        lessonSlug,
      };
    }
    rerender();
  } catch (e) {
    toast('载入失败：' + e.message, 'danger');
  }
}

async function submitCapstone() {
  const st = capstoneState[activeQid];
  if (!st) return;
  const text = (st.draft || '').trim();
  if (!text) { toast('先把答案写出来', 'danger'); return; }
  st.streaming = true;
  st.partial = '';
  st.parsed = null;
  rerender();
  const handle = analysesApi.stream(
    { question_id: st.question.id, user_text: text, source: 'capstone' },
    {
      onDelta: (_, full) => {
        st.partial = full;
        st.parsed = parseAnalysis(full);
        rerender();
      },
    },
  );
  try {
    const full = await handle.promise;
    const parsed = parseAnalysis(full);
    if (parsed.score == null) {
      toast('评估没返回分数', 'danger');
      st.streaming = false;
      rerender();
      return;
    }
    const created = await analysesApi.create({
      question_id: st.question.id,
      user_text: text,
      source: 'capstone',
      score: parsed.score,
      strengths: parsed.strengths,
      gaps: parsed.gaps,
      suggestions: parsed.suggestions,
      topics_touched: parsed.topics_touched,
    });
    st.history = [created, ...st.history];
    st.lastScore = parsed.score;
    st.streaming = false;
    st.partial = '';
    // 自动晋级：score >= 70 → passed；否则 in_progress
    const passed = parsed.score >= 70;
    await curriculumApi.putProgress(st.lessonSlug, {
      status: passed ? 'passed' : 'in_progress',
      capstone_score: parsed.score,
    });
    await reloadTree();
    toast(passed ? `通过！${parsed.score}/100` : `还差一些 · ${parsed.score}/100`, passed ? 'success' : 'info');
    rerender();
  } catch (e) {
    st.streaming = false;
    toast('评估失败：' + e.message, 'danger');
    rerender();
  }
}

function rerender() {
  // store 自带 subscribe，但 capstoneState 是局部的；用 router 的 refresh
  import('../app.js').then(({ router }) => router.refresh());
}

function renderTree() {
  const tree = curriculumStore.state.tree;
  if (!tree) return html`<div class="empty">没有 curriculum，先跑 <code>python -m scripts.seed_curriculum</code></div>`;
  const progressMap = {};
  for (const m of tree.modules) for (const l of m.lessons) {
    if (l.progress) progressMap[l.slug] = l.progress;
  }
  const totalLessons = tree.modules.reduce((s, m) => s + m.lessons.length, 0);
  const passedCount = Object.values(progressMap).filter(p => p.status === 'passed').length;

  return html`
    <div class="curr-track-head">
      <h2>${tree.name}</h2>
      <div class="curr-track-meta">
        进度 · <strong>${passedCount}</strong> / ${totalLessons} 课通过
      </div>
      <p class="curr-track-desc">${tree.description}</p>
    </div>
    ${raw(tree.modules.map(m => {
      const passed = m.lessons.filter(l => progressMap[l.slug]?.status === 'passed').length;
      return `
        <div class="curr-module">
          <div class="curr-module-head">
            <span class="curr-module-name">${escapeHtml(m.name)}</span>
            <span class="curr-module-prog">${passed}/${m.lessons.length}</span>
          </div>
          <div class="curr-module-desc">${escapeHtml(m.description || '')}</div>
          <ul class="curr-lesson-list">
            ${m.lessons.map(l => {
              const ok = isPrereqSatisfied(l, progressMap);
              const status = l.progress?.status || (ok ? 'available' : 'locked');
              const sel = selectedLessonSlug === l.slug ? 'selected' : '';
              const lockCls = !ok && status !== 'passed' ? 'locked' : '';
              return `
                <li class="curr-lesson ${sel} ${lockCls}" data-lesson="${escapeAttr(l.slug)}">
                  <span class="curr-lesson-num">${l.order_index}.</span>
                  <span class="curr-lesson-name">${escapeHtml(l.name)}</span>
                  <span class="curr-lesson-est">${l.est_minutes}m</span>
                  ${statusBadge({status})}
                </li>
              `;
            }).join('')}
          </ul>
        </div>
      `;
    }).join(''))}
  `;
}

function findLesson(slug) {
  const tree = curriculumStore.state.tree;
  if (!tree) return null;
  for (const m of tree.modules) for (const l of m.lessons) if (l.slug === slug) return l;
  return null;
}

function renderLessonDetail() {
  if (!selectedLessonSlug) {
    return html`<div class="curr-detail-empty">← 选一节课开始</div>`;
  }
  const lesson = findLesson(selectedLessonSlug);
  if (!lesson) return html`<div class="curr-detail-empty">未找到这节课</div>`;
  const progress = lesson.progress;
  const cap = capstoneState[activeQid];
  const showCap = cap && cap.lessonSlug === selectedLessonSlug;

  return html`
    <div class="curr-detail">
      <div class="curr-detail-head">
        <div>
          <h3>${lesson.name}</h3>
          <div class="curr-detail-meta">${lesson.est_minutes} min · ${statusBadge(progress)}</div>
        </div>
      </div>
      <div class="curr-concept">${raw(escapeHtml(lesson.concept_md).replace(/\n\n/g, '</p><p>').replace(/^/, '<p>') + '</p>')}</div>
      <div class="curr-capstone-section">
        <h4>★ 毕业题</h4>
        <div class="curr-capstone-prompt">${escapeHtml(lesson.capstone_prompt)}</div>
        ${!showCap ? html`
          <button class="btn primary" data-start-cap>▶ 开始作答</button>
        ` : html`
          <textarea class="curr-cap-ta" id="curr-cap-ta" placeholder="把你的答案写在这里…">${escapeHtml(cap.draft)}</textarea>
          <div class="curr-cap-actions">
            <button class="btn primary" data-submit-cap ${cap.streaming ? 'disabled' : ''}>
              ${cap.streaming ? '评估中…' : '提交并评估'}
            </button>
            ${cap.lastScore != null ? `<span class="curr-cap-score">${cap.lastScore}/100 ${cap.lastScore >= 70 ? '✓ PASSED' : '需要再练'}</span>` : ''}
          </div>
          ${cap.partial ? html`
            <div class="curr-cap-stream"><pre>${escapeHtml(cap.partial)}</pre></div>
          ` : ''}
          ${cap.history.length > 0 ? html`
            <div class="curr-cap-history">
              <h5>历史评估</h5>
              ${raw(cap.history.slice(0, 5).map(a => `
                <div class="curr-cap-h-item">
                  <span class="score">${a.score ?? '—'}</span>
                  <span class="when">${new Date(a.at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>
                </div>
              `).join(''))}
            </div>
          ` : ''}
        `}
      </div>
    </div>
  `;
}

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
    return html`
      <section class="view view-curriculum">
        <header class="page-head">
          <div class="page-num">005 / CURRICULUM</div>
          <h1 class="page-title">课程<span class="accent">.</span></h1>
          <p class="page-lede">系统补一块知识，按 lesson 走，毕业题不通过不算过。</p>
        </header>
        <div class="curr-grid">
          <aside class="curr-tree">${renderTree()}</aside>
          <main class="curr-detail-pane">${renderLessonDetail()}</main>
        </div>
      </section>
    `;
  },
  mount(root) {
    if (!curriculumStore.state.loaded) {
      loadCurriculum().then(() => rerender());
    }
    root.querySelectorAll('[data-lesson]').forEach(el => {
      el.addEventListener('click', () => {
        if (el.classList.contains('locked')) {
          toast('前置课没通过', 'danger');
          return;
        }
        selectedLessonSlug = el.dataset.lesson;
        activeQid = null;
        rerender();
      });
    });
    root.querySelector('[data-start-cap]')?.addEventListener('click', () => {
      startCapstone(selectedLessonSlug);
    });
    root.querySelector('[data-submit-cap]')?.addEventListener('click', () => {
      submitCapstone();
    });
    const ta = root.querySelector('#curr-cap-ta');
    if (ta && activeQid && capstoneState[activeQid]) {
      ta.addEventListener('input', (e) => {
        capstoneState[activeQid].draft = e.target.value;
      });
    }
  },
};
