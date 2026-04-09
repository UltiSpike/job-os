import { openModal, closeModal } from '../components/modal.js';
import { rateQuestion, questionsStore } from '../store/questions.js';
import { questionsApi } from '../api/questions.js';
import { answersApi } from '../api/answers.js';
import { analysesApi } from '../api/analyses.js';
import { chatApi } from '../api/chat.js';
import { llmApi } from '../api/llm.js';
import { settingsStore } from '../store/settings.js';
import { ASRClient } from '../lib/asrClient.js';
import { parseAnalysis } from '../lib/parseAnalysis.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';
import { escapeHtml } from '../components/html.js';
import { PROMPT_TEMPLATES, getDefaultTemplate, getTemplateById } from './_promptTemplates.js';

let session = null;
let asrClient = null;
let liveTranscript = '';
let activeGen = null;  // { abort, timer }
let lastTemplateId = getDefaultTemplate().id;  // 记住上次用的模板
let viewingVariantId = null; // 当前在看哪个模板的答案
let currentSubtab = 'answer';  // 'answer' | 'followup' | 'note'
let followupDraft = '';        // 保留追问输入框草稿，避免切 tab 丢失
let followupMode = 'chat';     // 'chat' | 'analyze' — 右栏的两个子模式
let analysisDraft = '';        // 评估时正在编辑的 user_text 草稿
let analysisSource = 'note';   // 评估时取哪个来源 'note' | 'speaking' | 'manual'
let activeAnalysis = null;     // 当前流式分析的临时状态 { partial, parsed }
let editingVariant = false;    // 是否正在 inline 编辑当前 variant
let variantDraft = '';         // 编辑中的草稿
let activeSessionId = null;    // 当前查看的追问会话 id

// ─── 题目级数据缓存 ─── 替代旧的 q.answer_variants / q.analyses / q.chat_sessions
// 每次切换题目时通过 dedicated APIs 重新拉取
let practiceData = {
  qid: null,
  answers: [],     // Answer[]
  analyses: [],    // Analysis[]
  sessions: [],    // [{id, question_id, title, variant_ref, created_at, updated_at, messages: []}]
  loaded: false,
};

async function loadPracticeData(qid) {
  if (!qid) return;
  practiceData = { qid, answers: [], analyses: [], sessions: [], loaded: false };
  const [ansR, anR, sessR] = await Promise.all([
    answersApi.listForQuestion(qid),
    analysesApi.listForQuestion(qid),
    chatApi.listSessions(qid),
  ]);
  // 拉每个 session 的消息
  const sessionMetas = sessR.items || [];
  const sessions = await Promise.all(sessionMetas.map(async s => {
    const detail = await chatApi.getSession(s.id).catch(() => ({ messages: [] }));
    return { ...s, messages: detail.messages || [] };
  }));
  practiceData = {
    qid,
    answers: ansR.items || [],
    analyses: anR.items || [],
    sessions,
    loaded: true,
  };
}

function getVariants(_q) {
  return practiceData.answers || [];
}
function findVariant(_q, tplId) {
  return getVariants().find(v => v.template_id === tplId) || null;
}

function getSessions(_q) {
  return practiceData.sessions || [];
}

function getActiveSession(_q) {
  const sessions = getSessions();
  if (sessions.length === 0) return null;
  if (activeSessionId) {
    const found = sessions.find(s => s.id === activeSessionId);
    if (found) return found;
  }
  return [...sessions].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))[0];
}

function getAnalyses(_q) {
  return practiceData.analyses || [];
}

function autoTitleFromMessage(text) {
  if (!text) return '新会话';
  const cleaned = text.replace(/\s+/g, ' ').trim();
  return cleaned.length <= 20 ? cleaned : cleaned.slice(0, 20) + '…';
}

function renderPane(q, answerHTML) {
  if (currentSubtab === 'answer') {
    return `
      <div class="prac-speak collapsed" id="prac-speak-section">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="prac-speak-toggle" id="prac-speak-toggle">🎙 口述模式</span>
          <span id="prac-mic-state" class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.06em">idle</span>
        </div>
        <div class="prac-speak-body" style="margin-top:8px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <button id="prac-mic" class="btn" style="font-size:10px;padding:6px 12px">开始录音</button>
            <button id="prac-mic-save" class="btn ghost" style="margin-left:auto;display:none;font-size:10px;padding:6px 12px">保存到 speaking_logs</button>
          </div>
          <div id="prac-live" class="prac-live" placeholder="实时转写…"></div>
        </div>
      </div>
      <div id="prac-answer-host">${answerHTML}</div>
    `;
  }
  if (currentSubtab === 'followup') {
    return `<div class="prac-followup" id="prac-followup-host"></div>`;
  }
  if (currentSubtab === 'note') {
    return `
      <div class="prac-note-pane">
        <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px">
          <span class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.1em;text-transform:uppercase">◇ 我的笔记 — 自动保存</span>
          <span id="prac-note-state" class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.05em"></span>
        </div>
        <textarea id="prac-note" placeholder="自己的想法、补充、要重点复习的点…">${escapeHtml(q.note || '')}</textarea>
      </div>
    `;
  }
  return '';
}

function followupCount(_q) {
  let n = 0;
  for (const s of getSessions()) {
    n += (s.messages || []).filter(m => m.role === 'user').length;
  }
  return n;
}
function pickInitialVariant(q) {
  const vs = getVariants(q);
  if (vs.length === 0) return null;
  // 优先 lastTemplateId，否则最近一次
  const last = vs.find(v => v.template_id === lastTemplateId);
  if (last) return last;
  return [...vs].sort((a, b) => (b.generated_at || '').localeCompare(a.generated_at || ''))[0];
}

export async function openPractice(queue, startIdx = 0) {
  if (!queue || queue.length === 0) {
    toast('当前过滤下没有可练习的题目', 'danger');
    return;
  }
  session = { queue, idx: startIdx, revealed: false };
  try {
    await loadPracticeData(current().id);
  } catch (e) {
    toast('加载题目数据失败：' + e.message, 'danger');
  }
  renderCard();
}

// 切换题目时刷新缓存
async function gotoIndex(newIdx) {
  if (newIdx < 0 || newIdx >= session.queue.length) return;
  session.idx = newIdx;
  session.revealed = false;
  await stopAsrIfRunning();
  try {
    await loadPracticeData(current().id);
  } catch (e) {
    toast('加载题目数据失败：' + e.message, 'danger');
  }
  renderCard();
}

function current() { return session.queue[session.idx]; }

function renderCard() {
  const q = current();
  const total = session.queue.length;

  const topics = (q.topics || []).map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join('');
  const ratingLine = q.rating
    ? `已评：<strong>${q.rating}</strong> · 第 ${q.review_count || 0} 轮`
    : '未评估';

  // 选当前展示的 variant
  const variants = getVariants(q);
  let currentVariant = null;
  if (viewingVariantId) currentVariant = findVariant(q, viewingVariantId);
  if (!currentVariant) currentVariant = pickInitialVariant(q);
  if (currentVariant) viewingVariantId = currentVariant.template_id;

  // tabs 行：每个模板一个 tab，已生成的有 ● 标记
  const tabsHTML = PROMPT_TEMPLATES.map(t => {
    const has = !!findVariant(q, t.id);
    const active = currentVariant && currentVariant.template_id === t.id;
    return `<button class="prac-tab ${active ? 'active' : ''} ${has ? 'has' : ''}" data-tab-tpl="${t.id}" title="${escapeHtml(t.desc)}">
      <span class="dot">${has ? '●' : '○'}</span>${escapeHtml(t.name)}
    </button>`;
  }).join('');

  let bodyHTML;
  if (!session.revealed && !currentVariant) {
    bodyHTML = `<button class="btn" id="prac-reveal">↓ 显示参考答案</button>`;
  } else if (currentVariant) {
    const editedBadge = currentVariant.user_edited
      ? `<span class="prac-edited-tag" title="已手动编辑过">✎ 已编辑</span>`
      : '';
    const answerBody = editingVariant
      ? `
        <div class="prac-answer-edit">
          <textarea id="prac-var-text" class="prac-var-textarea">${escapeHtml(variantDraft || currentVariant.content)}</textarea>
          <div class="prac-var-actions">
            <span class="prac-var-hint mono">编辑后标记为「已编辑」 · ESC 取消</span>
            <button class="btn ghost" id="prac-var-cancel">取消</button>
            <button class="btn primary" id="prac-var-save">保存</button>
          </div>
        </div>
      `
      : `
        <div class="prac-answer-wrap">
          <button class="prac-answer-edit-btn" id="prac-var-edit" title="编辑此答案">✎</button>
          <div class="prac-answer">${escapeHtml(currentVariant.content).replace(/\n/g, '<br>')}</div>
        </div>
      `;
    bodyHTML = `
      <div class="prac-tabs">${tabsHTML}</div>
      ${answerBody}
      <div class="prac-regen">
        <span class="prac-meta mono">▸ ${escapeHtml(currentVariant.template_name)} ${editedBadge} · ${new Date(currentVariant.edited_at || currentVariant.generated_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>
        <button class="btn ghost" id="prac-regen-current" style="font-size:9px;padding:3px 8px">↻ 重新生成</button>
        <button class="btn ghost" id="prac-var-del" style="font-size:9px;padding:3px 8px;margin-left:auto" title="删除当前模板的答案">✕ 删除</button>
      </div>
    `;
  } else {
    // session.revealed && !currentVariant — 没生成过任何模板
    bodyHTML = `
      <div class="prac-tabs">${tabsHTML}</div>
      <div class="prac-answer empty">
        <div class="dim mono" style="font-size:11px;margin-bottom:10px">暂无答案 — 点击下方按钮用「${escapeHtml(getDefaultTemplate().name)}」生成</div>
        <button class="btn" id="prac-gen">⚙ AI 生成答案</button>
      </div>
    `;
  }
  const answerHTML = bodyHTML;

  openModal({
    wide: true,
    title: `练习 ${session.idx + 1} / ${total}`,
    sub: ratingLine,
    body: `
      <style>
        .prac-q {
          font-family: var(--font-serif);
          font-size: 22px;
          line-height: 1.4;
          color: var(--char);
          padding: 10px 0 16px;
          border-bottom: 1px solid var(--line-paper);
          margin-bottom: 14px;
          font-variation-settings: "opsz" 144, "SOFT" 30;
        }
        .prac-topics { margin-bottom: 12px; display: flex; gap: 6px; flex-wrap: wrap; }

        /* ─── 双栏布局 ─── */
        .prac-split {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 0;
          border: 1px solid var(--char);
          margin-bottom: 12px;
        }
        .prac-col {
          display: flex;
          flex-direction: column;
          min-width: 0; /* 防 grid 子项撑爆 */
        }
        .prac-col-answer {
          border-right: 1px solid var(--char);
          background: rgba(196, 123, 42, 0.03);
        }
        .prac-col-followup {
          background: rgba(26, 22, 18, 0.02);
        }
        .prac-col-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          border-bottom: 1px dashed var(--line-paper-2);
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .prac-col-head .col-label { color: var(--char); font-weight: 600; }
        .prac-col-body {
          padding: 16px 18px 18px;
          flex: 1;
          min-height: 56vh;
          max-height: 62vh;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
        }
        .topic-tag {
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          padding: 2px 7px;
          border: 1px solid var(--line-paper-2);
          color: var(--char-soft);
        }
        .prac-answer {
          background: transparent;
          border-left: 2px solid var(--amber);
          padding: 10px 14px;
          font-family: var(--font-serif);
          font-size: 14px;
          line-height: 1.6;
          color: var(--char);
          margin: 8px 0 4px;
          white-space: pre-wrap;
        }
        .prac-answer-wrap {
          position: relative;
        }
        .prac-answer-wrap:hover .prac-answer-edit-btn { opacity: 1; }
        .prac-answer-edit-btn {
          position: absolute;
          top: 4px;
          right: 4px;
          opacity: 0;
          transition: opacity 0.18s var(--ease);
          font-family: var(--font-mono);
          font-size: 11px;
          width: 24px;
          height: 24px;
          border: 1px solid var(--line-paper-2);
          background: var(--paper);
          color: var(--char-soft);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .prac-answer-edit-btn:hover {
          color: var(--amber-soft);
          border-color: var(--amber);
        }
        .prac-answer-edit {
          margin: 8px 0 4px;
        }
        .prac-var-textarea {
          width: 100%;
          min-height: 200px;
          padding: 12px 14px;
          background: rgba(196, 123, 42, 0.04);
          border: 1px solid var(--amber);
          border-left-width: 2px;
          color: var(--char);
          font-family: var(--font-serif);
          font-size: 14px;
          line-height: 1.6;
          resize: vertical;
          outline: none;
        }
        .prac-var-actions {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 8px;
        }
        .prac-var-hint {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.05em;
          margin-right: auto;
        }
        .prac-edited-tag {
          font-family: var(--font-mono);
          font-size: 8px;
          letter-spacing: 0.06em;
          padding: 1px 5px;
          border: 1px solid var(--amber);
          color: var(--amber-soft);
          margin-left: 6px;
        }
        .prac-answer.empty {
          background: transparent;
          border-left-color: var(--line-paper-2);
          font-style: italic;
        }
        .prac-tabs {
          display: flex;
          gap: 0;
          margin: 4px 0 0;
          flex-wrap: wrap;
        }
        .prac-tab {
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          padding: 6px 10px;
          border: 1px solid var(--line-paper-2);
          margin: 0 -1px -1px 0;
          color: var(--char-soft);
          background: transparent;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 5px;
        }
        .prac-tab .dot { color: var(--line-paper-2); font-size: 8px; }
        .prac-tab.has .dot { color: var(--sage); }
        .prac-tab:hover { color: var(--char); }
        .prac-tab.active {
          color: var(--amber-soft);
          border-color: var(--amber);
          background: rgba(196, 123, 42, 0.06);
          z-index: 1;
          position: relative;
        }
        .prac-tab.active .dot { color: var(--amber); }
        .prac-regen {
          margin-top: 10px;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .prac-meta {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.05em;
          text-transform: uppercase;
        }
        .btn.ghost {
          border-color: var(--line-paper-2);
          color: var(--char-soft);
        }

        /* ─── 追问 (multi-session) ─── */
        .prac-fu-noctx {
          padding: 40px 0;
          text-align: center;
          color: var(--char-soft);
          font-family: var(--font-serif);
          font-style: italic;
        }
        .prac-fu-noctx .mono {
          font-family: var(--font-mono);
          font-size: 11px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--rust);
          margin-bottom: 8px;
          font-style: normal;
        }
        .prac-fu-noctx .hint { font-size: 13px; }

        /* host 是 col-body，需要纵向 flex 让 input sticky 在底部 */
        #prac-followup-host {
          display: flex !important;
          flex-direction: column !important;
          padding: 0 !important;
          height: 100%;
        }

        /* session bar */
        .prac-fu-bar {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 14px;
          border-bottom: 1px dashed var(--line-paper-2);
          flex-shrink: 0;
        }
        .prac-fu-session-select {
          flex: 1;
          position: relative;
          min-width: 0;
        }
        .prac-fu-session-current {
          display: flex;
          align-items: center;
          gap: 6px;
          width: 100%;
          padding: 6px 10px;
          background: transparent;
          border: 1px solid var(--line-paper-2);
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--char);
          cursor: pointer;
          text-align: left;
          transition: all 0.15s var(--ease);
        }
        .prac-fu-session-current:hover { border-color: var(--amber); }
        .prac-fu-session-current .ic { color: var(--amber); font-size: 9px; }
        .prac-fu-session-current .nm {
          flex: 1;
          font-family: var(--font-serif);
          font-size: 13px;
          color: var(--char);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .prac-fu-session-current .cnt {
          font-size: 9px;
          color: var(--char-soft);
          padding: 1px 5px;
          border: 1px solid var(--line-paper-2);
        }
        .prac-fu-session-current .caret { color: var(--char-soft); }

        .prac-fu-session-menu {
          position: absolute;
          top: calc(100% + 4px);
          left: 0;
          right: 0;
          z-index: 10;
          background: var(--paper);
          border: 1px solid var(--char-soft);
          box-shadow: 6px 6px 0 var(--ink);
          max-height: 280px;
          overflow-y: auto;
        }
        .prac-fu-session-menu .empty {
          padding: 14px;
          font-style: italic;
          color: var(--char-soft);
          font-size: 12px;
          text-align: center;
        }
        .sess-item {
          display: grid;
          grid-template-columns: 1fr auto auto auto;
          gap: 8px;
          align-items: center;
          padding: 10px 12px;
          border-bottom: 1px dashed var(--line-paper-2);
          cursor: pointer;
          transition: background 0.15s var(--ease);
        }
        .sess-item:last-child { border-bottom: 0; }
        .sess-item:hover { background: rgba(196, 123, 42, 0.06); }
        .sess-item.active { background: rgba(196, 123, 42, 0.1); }
        .sess-item .sess-name {
          font-family: var(--font-serif);
          font-size: 13px;
          color: var(--char);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sess-item.active .sess-name { color: var(--amber-soft); font-weight: 600; }
        .sess-item .sess-cnt {
          font-size: 9px;
          color: var(--char-soft);
        }
        .sess-item .sess-rename,
        .sess-item .sess-del {
          font-family: var(--font-mono);
          font-size: 10px;
          padding: 2px 6px;
          background: transparent;
          border: 1px solid var(--line-paper-2);
          color: var(--char-soft);
          cursor: pointer;
        }
        .sess-item .sess-rename:hover { color: var(--amber); border-color: var(--amber); }
        .sess-item .sess-del:hover { color: var(--rust); border-color: var(--rust); }

        .prac-fu-new-session {
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.06em;
          padding: 6px 12px;
          background: var(--char);
          color: var(--paper);
          border: 1px solid var(--char);
          cursor: pointer;
          flex-shrink: 0;
        }
        .prac-fu-new-session:hover { background: var(--amber-soft); border-color: var(--amber-soft); }

        /* 上下文提示行 */
        .prac-fu-ctx-hint {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.04em;
          padding: 6px 14px;
          border-bottom: 1px dashed var(--line-paper-2);
          background: rgba(196, 123, 42, 0.03);
          flex-shrink: 0;
        }

        /* thread 区 — 这是会滚动的区域 */
        .prac-fu-thread-area {
          flex: 1 1 auto;
          overflow-y: auto;
          padding: 14px 14px 6px;
          min-height: 0;
        }

        .prac-fu-empty {
          padding: 40px 14px;
          text-align: center;
          color: var(--char-soft);
        }
        .prac-fu-empty .hint {
          font-family: var(--font-serif);
          font-style: italic;
          font-size: 14px;
          color: var(--char-soft);
          margin-bottom: 6px;
        }
        .prac-fu-empty .sub {
          font-size: 9px;
          letter-spacing: 0.06em;
          color: var(--char-soft);
          opacity: 0.6;
        }
        .prac-fu-mode-toggle {
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.06em;
          color: var(--char-soft);
          cursor: pointer;
          text-transform: uppercase;
          padding: 2px 8px;
          border: 1px solid var(--line-paper-2);
        }
        .prac-fu-mode-toggle:hover {
          color: var(--amber-soft);
          border-color: var(--amber);
        }

        /* ─── 评估面板 ─── */
        .prac-an-srcbar {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 10px;
          font-family: var(--font-mono);
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }
        .prac-an-srcbar .lbl { margin-right: 4px; }
        .prac-an-srcbar .src {
          padding: 3px 8px;
          border: 1px solid var(--line-paper-2);
          background: transparent;
          font-family: inherit;
          font-size: 9px;
          letter-spacing: inherit;
          text-transform: inherit;
          color: var(--char-soft);
          cursor: pointer;
        }
        .prac-an-srcbar .src:hover { color: var(--char); }
        .prac-an-srcbar .src.active {
          color: var(--amber-soft);
          border-color: var(--amber);
          background: rgba(196, 123, 42, 0.06);
        }
        .prac-an-srcbar .hist { margin-left: auto; font-size: 9px; }
        .prac-an-text {
          width: 100%;
          min-height: 80px;
          padding: 10px 12px;
          background: rgba(26, 22, 18, 0.03);
          border: 1px solid var(--line-paper-2);
          color: var(--char);
          font-family: var(--font-serif);
          font-size: 13px;
          line-height: 1.55;
          resize: vertical;
          outline: none;
          margin-bottom: 8px;
        }
        .prac-an-text:focus { border-color: var(--amber); }
        .prac-an-actions { display: flex; gap: 8px; margin-bottom: 14px; }
        .prac-an-result {
          border-top: 1px dashed var(--line-paper-2);
          padding-top: 14px;
          margin-top: 4px;
        }
        .prac-an-score {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding-bottom: 12px;
          margin-bottom: 12px;
          border-bottom: 1px solid var(--line-paper);
        }
        .prac-an-score .num {
          font-family: var(--font-serif);
          font-style: italic;
          font-variation-settings: "opsz" 144;
          font-size: 56px;
          line-height: 0.9;
          color: var(--char);
          font-weight: 400;
        }
        .prac-an-score.high .num { color: #4a7c4a; }
        .prac-an-score.mid  .num { color: var(--amber-soft); }
        .prac-an-score.low  .num { color: var(--rust); }
        .prac-an-score .label {
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--char-soft);
          letter-spacing: 0.06em;
        }
        .prac-an-block { margin-bottom: 12px; }
        .prac-an-block .hdr {
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          margin-bottom: 6px;
        }
        .prac-an-block .hdr.good { color: #4a7c4a; }
        .prac-an-block .hdr.bad  { color: var(--rust); }
        .prac-an-block .hdr.arrow { color: var(--amber-soft); }
        .prac-an-block ul { list-style: none; padding: 0; margin: 0; }
        .prac-an-block li {
          font-family: var(--font-serif);
          font-size: 13.5px;
          line-height: 1.5;
          color: var(--char);
          padding: 4px 0 4px 14px;
          position: relative;
        }
        .prac-an-block li::before {
          content: "·";
          position: absolute;
          left: 4px;
          color: var(--char-soft);
        }
        .prac-an-block p {
          font-family: var(--font-serif);
          font-size: 13.5px;
          line-height: 1.6;
          color: var(--char);
          font-style: italic;
          padding-left: 10px;
          border-left: 2px solid var(--amber);
        }
        .prac-an-topics { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px; }
        .prac-an-topics .t {
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.06em;
          padding: 2px 7px;
          border: 1px solid var(--line-paper-2);
          color: var(--char-soft);
          text-transform: uppercase;
        }
        .prac-an-history {
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px dashed var(--line-paper-2);
        }
        .prac-an-history .hdr {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.1em;
          text-transform: uppercase;
          margin-bottom: 6px;
        }
        .prac-an-history .hist-item {
          display: flex;
          align-items: baseline;
          gap: 10px;
          padding: 4px 0;
          font-family: var(--font-mono);
          font-size: 10px;
          color: var(--char-soft);
          border-bottom: 1px dashed var(--line-paper-2);
        }
        .prac-an-history .hist-item:last-child { border-bottom: 0; }
        .prac-an-history .hist-item { position: relative; }
        .prac-an-history .score {
          font-family: var(--font-serif);
          font-size: 14px;
          color: var(--char);
          min-width: 24px;
        }
        .prac-an-history .src { margin-left: auto; opacity: 0.7; }
        .prac-an-history .hist-del {
          opacity: 0;
          transition: opacity 0.18s var(--ease);
          font-family: var(--font-mono);
          font-size: 10px;
          width: 20px;
          height: 20px;
          border: 1px solid var(--line-paper-2);
          background: transparent;
          color: var(--char-soft);
          cursor: pointer;
          padding: 0;
          margin-left: 4px;
        }
        .prac-an-history .hist-item:hover .hist-del { opacity: 1; }
        .prac-an-history .hist-del:hover { color: var(--rust); border-color: var(--rust); }

        /* ─── 相关弱项题 ─── */
        .prac-an-related {
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px dashed var(--line-paper-2);
        }
        .prac-an-related .hdr {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.1em;
          text-transform: uppercase;
          margin-bottom: 8px;
        }
        .rel-q {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 8px 10px;
          margin-bottom: 4px;
          border: 1px solid var(--line-paper-2);
          background: transparent;
          width: 100%;
          text-align: left;
          cursor: pointer;
          transition: all 0.18s var(--ease);
          font-family: var(--font-serif);
        }
        .rel-q:hover {
          border-color: var(--amber);
          background: rgba(196, 123, 42, 0.06);
        }
        .rel-q .rel-arrow { color: var(--amber); font-family: var(--font-mono); font-size: 11px; }
        .rel-q .rel-text { flex: 1; font-size: 13px; color: var(--char); }
        .rel-q .rel-tag {
          font-family: var(--font-mono);
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }
        .prac-fu-thread {
          display: flex;
          flex-direction: column;
          gap: 14px;
        }
        .prac-fu-msg {
          font-family: var(--font-serif);
          font-size: 14px;
          line-height: 1.6;
          color: var(--char);
          font-variation-settings: "SOFT" 30;
          padding: 10px 14px;
          border-left: 2px solid transparent;
          position: relative;
        }
        .prac-fu-msg.user {
          border-left-color: var(--char-soft);
          background: rgba(26, 22, 18, 0.03);
          font-style: italic;
          color: var(--char-dim);
        }
        .prac-fu-msg.assistant {
          border-left-color: var(--amber);
          background: rgba(196, 123, 42, 0.04);
        }
        .prac-fu-msg .msg-head {
          display: flex;
          align-items: baseline;
          gap: 8px;
          margin-bottom: 6px;
        }
        .prac-fu-msg .msg-content {
          white-space: pre-wrap;
        }
        .prac-fu-msg .role {
          display: inline-block;
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--char-soft);
          padding: 1px 6px;
          border: 1px solid var(--line-paper-2);
        }
        .prac-fu-msg .msg-time {
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.04em;
        }
        .prac-fu-msg-del {
          margin-left: auto;
          opacity: 0;
          transition: opacity 0.18s var(--ease);
          font-family: var(--font-mono);
          font-size: 10px;
          padding: 2px 6px;
          border: 1px solid var(--line-paper-2);
          background: transparent;
          color: var(--char-soft);
          cursor: pointer;
        }
        .prac-fu-msg:hover .prac-fu-msg-del { opacity: 1; }
        .prac-fu-msg-del:hover { color: var(--rust); border-color: var(--rust); }
        .prac-fu-msg.user .role {
          color: var(--char);
          border-color: var(--char-soft);
        }
        .prac-fu-msg.assistant .role {
          color: var(--amber-soft);
          border-color: var(--amber);
        }
        .prac-fu-msg.user { font-style: italic; color: var(--char-dim); }

        .prac-fu-input-wrap {
          flex-shrink: 0;
          padding: 12px 14px;
          border-top: 1px solid var(--line-paper-2);
          background: var(--paper);
        }
        .prac-fu-input {
          position: relative;
          border: 1px solid var(--line-paper-2);
          background: var(--paper);
          transition: border-color 0.18s var(--ease);
        }
        .prac-fu-input:focus-within {
          border-color: var(--amber);
        }
        .prac-fu-input textarea {
          width: 100%;
          min-height: 48px;
          max-height: 160px;
          padding: 12px 60px 28px 14px;
          background: transparent;
          border: 0;
          color: var(--char);
          font-family: var(--font-serif);
          font-size: 14px;
          line-height: 1.5;
          resize: none;
          outline: none;
          display: block;
          font-variation-settings: "SOFT" 30;
        }
        .prac-fu-input textarea::placeholder {
          color: var(--char-soft);
          font-style: italic;
        }
        .prac-fu-hint {
          position: absolute;
          left: 14px;
          bottom: 6px;
          font-family: var(--font-mono);
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.06em;
          pointer-events: none;
        }
        .prac-fu-send {
          position: absolute;
          right: 8px;
          bottom: 6px;
          font-family: var(--font-mono);
          font-size: 9px;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          padding: 5px 12px;
          border: 1px solid var(--char);
          background: var(--char);
          color: var(--paper);
          cursor: pointer;
          transition: all 0.15s var(--ease);
        }
        .prac-fu-send:hover {
          background: var(--amber-soft);
          border-color: var(--amber-soft);
        }
        .prac-fu-send:disabled {
          opacity: 0.3;
          cursor: not-allowed;
        }

        .prac-fu-toggle {
          margin-top: 14px;
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.08em;
          color: var(--char-soft);
          cursor: pointer;
          border-bottom: 1px dashed var(--line-paper-2);
          padding-bottom: 2px;
          display: inline-block;
          transition: all 0.18s var(--ease);
        }
        .prac-fu-toggle:hover {
          color: var(--amber-soft);
          border-bottom-color: var(--amber);
          border-bottom-style: solid;
        }

        /* ─── 笔记 ─── */
        .prac-note { margin-top: 10px; }
        .prac-note.collapsed .prac-note-body { display: none; }
        .prac-note-head {
          display: flex;
          align-items: center;
          gap: 10px;
          cursor: pointer;
          padding: 4px 0;
        }
        .prac-note-head:hover .prac-note-label { color: var(--amber-soft); }
        .prac-note-label {
          font-family: var(--font-mono);
          font-size: 9px;
          color: var(--char-soft);
          letter-spacing: 0.1em;
          text-transform: uppercase;
          transition: color 0.18s var(--ease);
        }
        .prac-note-arrow {
          font-family: var(--font-mono);
          font-size: 9px;
          color: var(--char-soft);
        }
        .prac-note textarea {
          width: 100%;
          min-height: 56px;
          max-height: 200px;
          padding: 8px 12px;
          margin-top: 6px;
          background: rgba(26, 22, 18, 0.03);
          border: 1px solid var(--line-paper-2);
          color: var(--char);
          font-family: var(--font-serif);
          font-size: 13px;
          line-height: 1.5;
          resize: vertical;
          outline: none;
        }
        .prac-note textarea:focus { border-color: var(--amber); }
        .btn.ghost:hover { color: var(--amber); border-color: var(--amber); }
        .prac-speak {
          padding: 0 14px;
          border-bottom: 1px dashed var(--line-paper-2);
        }
        .prac-speak.collapsed { padding: 0; border-bottom: 0; }
        .prac-speak.collapsed .prac-speak-body { display: none; }
        .prac-speak-body { padding: 10px 0; }
        .prac-speak-toggle {
          font-family: var(--font-mono);
          font-size: 10px;
          letter-spacing: 0.08em;
          color: var(--char-soft);
          cursor: pointer;
          text-transform: uppercase;
        }
        .prac-speak-toggle:hover { color: var(--amber-soft); }
        .prac-live {
          min-height: 44px;
          padding: 8px 12px;
          background: rgba(12, 10, 8, 0.04);
          font-family: var(--font-serif);
          font-size: 13.5px;
          line-height: 1.5;
          color: var(--char);
          border-left: 2px solid var(--line-paper-2);
          font-variation-settings: "SOFT" 50;
        }
        .prac-live:empty::before {
          content: attr(placeholder);
          color: var(--char-soft);
          font-style: italic;
        }
        .prac-live.active { border-left-color: var(--rust); }
        .prac-rate {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-top: 14px;
        }
        .prac-rate .btn { justify-content: center; padding: 10px 0; font-size: 11px; }
        .prac-nav {
          display: flex;
          justify-content: space-between;
          margin-top: 10px;
          font-family: var(--font-mono);
          font-size: 10px;
          color: var(--char-soft);
        }
        .prac-nav button { color: var(--char-soft); padding: 4px 8px; border: 1px solid var(--line-paper-2); }
        .prac-nav button:disabled { opacity: 0.3; cursor: not-allowed; }
        .prac-nav button:hover:not(:disabled) { color: var(--amber); border-color: var(--amber); }
      </style>
      <div class="prac-q">${escapeHtml(q.text)}</div>
      <div class="prac-topics">${topics || '<span class="dim mono" style="font-size:10px">无标签</span>'}</div>

      <div class="prac-split">
        <section class="prac-col prac-col-answer">
          <div class="prac-col-head">
            <span class="col-label">◆ 答案</span>
            <span class="prac-speak-toggle" id="prac-speak-toggle">🎙 口述</span>
          </div>
          <div class="prac-speak collapsed" id="prac-speak-section">
            <div class="prac-speak-body">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                <button id="prac-mic" class="btn" style="font-size:10px;padding:5px 11px">开始录音</button>
                <span id="prac-mic-state" class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.06em">idle</span>
                <button id="prac-mic-save" class="btn ghost" style="margin-left:auto;display:none;font-size:10px;padding:5px 11px">保存</button>
              </div>
              <div id="prac-live" class="prac-live" placeholder="实时转写…"></div>
            </div>
          </div>
          <div id="prac-answer-host" class="prac-col-body">${answerHTML}</div>
        </section>

        <section class="prac-col prac-col-followup">
          <div class="prac-col-head">
            <span class="col-label">◇ 提问 / 评估</span>
            <span class="prac-fu-mode-toggle" id="prac-fu-mode-toggle">${followupMode === 'analyze' ? '回到提问' : '🔍 评估我的回答'}</span>
          </div>
          <div id="prac-followup-host" class="prac-col-body"></div>
        </section>
      </div>

      <div class="prac-note ${q.note ? '' : 'collapsed'}" id="prac-note-section">
        <div class="prac-note-head" id="prac-note-toggle">
          <span class="prac-note-arrow">▸</span>
          <span class="prac-note-label">◇ 我的笔记 ${q.note ? `<span style="color:var(--char-soft);font-style:italic;text-transform:none;letter-spacing:0">· ${q.note.length} 字</span>` : ''}</span>
          <span id="prac-note-state" class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.05em;margin-left:auto"></span>
        </div>
        <div class="prac-note-body">
          <textarea id="prac-note" placeholder="自己的想法、补充、要重点复习的点…">${escapeHtml(q.note || '')}</textarea>
        </div>
      </div>

      <div class="prac-rate">
        <button class="btn" data-rate="bad" style="border-color:rgba(168,51,43,0.5);color:var(--rust)">不会 · +1d</button>
        <button class="btn" data-rate="ok" style="border-color:var(--amber);color:var(--amber)">一般 · +3d</button>
        <button class="btn" data-rate="good" style="border-color:#6b8e6b;color:#6b8e6b">熟练 · +7d</button>
      </div>
      <div class="prac-nav">
        <button id="prac-prev" ${session.idx === 0 ? 'disabled' : ''}>← 上一题</button>
        <span>${session.idx + 1} / ${total}</span>
        <button id="prac-next" ${session.idx >= total - 1 ? 'disabled' : ''}>下一题 →</button>
      </div>
    `,
    actions: '',
    onMount(card) {
      card.querySelector('#prac-reveal')?.addEventListener('click', () => {
        session.revealed = true;
        renderCard();
      });

      card.querySelector('#prac-gen')?.addEventListener('click', () => startGeneration(card, q, lastTemplateId));

      // 模板 tab：已生成的直接切换；未生成的触发生成
      card.querySelectorAll('[data-tab-tpl]').forEach(btn => {
        btn.addEventListener('click', () => {
          const tplId = btn.dataset.tabTpl;
          const existing = findVariant(q, tplId);
          if (existing) {
            viewingVariantId = tplId;
            lastTemplateId = tplId;
            renderCard();
          } else {
            lastTemplateId = tplId;
            startGeneration(card, q, tplId);
          }
        });
      });

      // 重新生成当前模板
      card.querySelector('#prac-regen-current')?.addEventListener('click', () => {
        if (viewingVariantId) startGeneration(card, q, viewingVariantId);
      });

      // inline 编辑当前 variant
      card.querySelector('#prac-var-edit')?.addEventListener('click', () => {
        const v = findVariant(q, viewingVariantId);
        if (!v) return;
        editingVariant = true;
        variantDraft = v.content;
        renderCard();
      });

      card.querySelector('#prac-var-cancel')?.addEventListener('click', () => {
        editingVariant = false;
        variantDraft = '';
        renderCard();
      });

      card.querySelector('#prac-var-save')?.addEventListener('click', async () => {
        const text = card.querySelector('#prac-var-text').value;
        if (!text.trim()) {
          toast('内容不能为空', 'danger');
          return;
        }
        try {
          const target = findVariant(q, viewingVariantId);
          if (!target) throw new Error('找不到当前 variant');
          const updated = await answersApi.patch(target.id, text);
          // 更新本地缓存
          practiceData.answers = practiceData.answers.map(a => a.id === updated.id ? updated : a);
          // 同步 question.answer 字段（最近一次编辑作为主答案）
          await questionsApi.patch(q.id, { answer: text });
          q.answer = text;
          editingVariant = false;
          variantDraft = '';
          toast('已保存', 'success');
          renderCard();
        } catch (e) { toast('保存失败：' + e.message, 'danger'); }
      });

      // ESC 退出编辑
      if (editingVariant) {
        const escHandler = (e) => {
          if (e.key === 'Escape') {
            editingVariant = false;
            variantDraft = '';
            document.removeEventListener('keydown', escHandler);
            renderCard();
          }
        };
        document.addEventListener('keydown', escHandler);
      }

      // 删除当前 variant（带 undo）
      card.querySelector('#prac-var-del')?.addEventListener('click', async () => {
        const v = findVariant(q, viewingVariantId);
        if (!v) return;
        try {
          const r = await answersApi.delete(v.id);
          const snapshot = r.snapshot;
          practiceData.answers = practiceData.answers.filter(x => x.id !== v.id);
          viewingVariantId = practiceData.answers[0]?.template_id || null;
          renderCard();
          undoableToast(`已删除「${v.template_name}」的答案`, async () => {
            const restored = await answersApi.restore(snapshot);
            practiceData.answers = [...practiceData.answers, restored];
            viewingVariantId = restored.template_id;
            renderCard();
            toast('已恢复', 'success');
          }, { kind: 'success' });
        } catch (e) { toast('删除失败：' + e.message, 'danger'); }
      });

      card.querySelectorAll('[data-rate]').forEach(el => {
        el.addEventListener('click', async () => {
          const r = el.dataset.rate;
          try {
            await rateQuestion(q.id, r);
            if (session.idx < session.queue.length - 1) {
              await gotoIndex(session.idx + 1);
            } else {
              closeModal();
              toast(`本轮完成 · ${session.queue.length} 题`, 'success');
              router.refresh();
            }
          } catch (e) { toast(e.message, 'danger'); }
        });
      });

      card.querySelector('#prac-prev')?.addEventListener('click', () => gotoIndex(session.idx - 1));
      card.querySelector('#prac-next')?.addEventListener('click', () => gotoIndex(session.idx + 1));

      // 折叠：口述模式 + 笔记
      const speakSec = card.querySelector('#prac-speak-section');
      card.querySelector('#prac-speak-toggle')?.addEventListener('click', () => {
        speakSec?.classList.toggle('collapsed');
      });
      const noteSec = card.querySelector('#prac-note-section');
      card.querySelector('#prac-note-toggle')?.addEventListener('click', (e) => {
        if (e.target.tagName !== 'TEXTAREA') noteSec?.classList.toggle('collapsed');
      });

      // 右栏模式切换
      card.querySelector('#prac-fu-mode-toggle')?.addEventListener('click', () => {
        followupMode = followupMode === 'analyze' ? 'chat' : 'analyze';
        renderCard();
      });

      // 双栏全部 bind（同时存在）
      bindAsrControls(card, q);
      bindFollowup(card, q);
      bindNote(card, q);
      bindAnalyze(card, q);
      renderRightColumn(card, q);
    },
  });
}

// ─── 右栏渲染分发：追问 vs 评估 ───
function renderRightColumn(card, q) {
  if (followupMode === 'analyze') {
    renderAnalyzePane(card, q);
  } else {
    renderFollowupThread(card, q);
  }
}

// ─── 评估面板 ───
function renderAnalyzePane(card, q) {
  const host = card.querySelector('#prac-followup-host');
  if (!host) return;

  // 历史 analyses —— 走 practiceData
  const history = getAnalyses();
  // 默认 user_text 来源
  const speakingLogs = Array.isArray(q.speaking_logs) ? q.speaking_logs : [];
  let defaultText = analysisDraft;
  if (!defaultText) {
    if (analysisSource === 'speaking' && speakingLogs.length > 0) {
      defaultText = speakingLogs[speakingLogs.length - 1].text || '';
    } else if (analysisSource === 'note' && q.note) {
      defaultText = q.note;
    }
  }

  // 显示流式中或最近一次结果
  const showLive = activeAnalysis && activeAnalysis.parsed;
  const latest = history[history.length - 1];

  const renderResult = (a) => {
    if (!a) return '';
    const scoreCls = a.score >= 80 ? 'high' : a.score >= 60 ? 'mid' : 'low';
    // 找相关的弱项题（同 topic + 之前评低 / 没评 / rated bad）
    const relatedTopics = a.topics_touched || [];
    const allQs = questionsStore.state.questions || [];
    const related = relatedTopics.length === 0 ? [] : allQs.filter(rq => {
      if (rq.id === q.id) return false;
      const qTopics = rq.topics || [];
      const overlap = relatedTopics.some(t => qTopics.some(qt => qt.toLowerCase().includes(t.toLowerCase()) || t.toLowerCase().includes(qt.toLowerCase())));
      if (!overlap) return false;
      // 弱项标准：rated bad / 没 rating / 平均 analysis 分 < 70
      if (rq.rating === 'bad') return true;
      if (!rq.rating) return true;
      // 用 store 里跨题预聚合的 recentAnalyses（不再读 q.analyses）
      const all = (questionsStore.state.recentAnalyses || []).filter(a => a.question_id === rq.id);
      const avg = all.length > 0 ? all.reduce((s, x) => s + (x.score || 0), 0) / all.length : null;
      if (avg != null && avg < 70) return true;
      return false;
    }).slice(0, 5);

    return `
      <div class="prac-an-result">
        <div class="prac-an-score ${scoreCls}">
          <span class="num">${a.score ?? '—'}</span>
          <span class="label">/ 100</span>
        </div>
        ${(a.strengths || []).length > 0 ? `
          <div class="prac-an-block">
            <div class="hdr good">✓ 强项</div>
            <ul>${a.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
          </div>` : ''}
        ${(a.gaps || []).length > 0 ? `
          <div class="prac-an-block">
            <div class="hdr bad">✗ 缺口</div>
            <ul>${a.gaps.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
          </div>` : ''}
        ${a.suggestions ? `
          <div class="prac-an-block">
            <div class="hdr arrow">→ 下次重点</div>
            <p>${escapeHtml(a.suggestions)}</p>
          </div>` : ''}
        ${(a.topics_touched || []).length > 0 ? `
          <div class="prac-an-topics">
            ${a.topics_touched.map(t => `<span class="t">${escapeHtml(t)}</span>`).join('')}
          </div>` : ''}
        ${related.length > 0 ? `
          <div class="prac-an-related">
            <div class="hdr mono">△ 相关弱项题 (${related.length})</div>
            ${related.map(rq => `
              <button class="rel-q" data-rel-q="${escapeHtml(rq.id)}">
                <span class="rel-arrow">→</span>
                <span class="rel-text">${escapeHtml(rq.text.slice(0, 38))}${rq.text.length > 38 ? '…' : ''}</span>
                <span class="rel-tag">${rq.rating || '未评'}</span>
              </button>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  };

  host.innerHTML = `
    <div class="prac-an-srcbar">
      <span class="lbl">来源：</span>
      <button class="src ${analysisSource === 'note' ? 'active' : ''}" data-src="note">笔记</button>
      <button class="src ${analysisSource === 'speaking' ? 'active' : ''}" data-src="speaking">最近口述</button>
      <button class="src ${analysisSource === 'manual' ? 'active' : ''}" data-src="manual">手动粘贴</button>
      ${history.length > 0 ? `<span class="hist mono">已有 ${history.length} 次评估</span>` : ''}
    </div>
    <textarea id="prac-an-text" class="prac-an-text" rows="4" placeholder="把你的回答贴/写在这里 — 默认从所选来源载入">${escapeHtml(defaultText)}</textarea>
    <div class="prac-an-actions">
      <button class="prac-fu-send" id="prac-an-run">${activeAnalysis ? '⋯ 分析中' : '▶ 开始分析'}</button>
      ${activeAnalysis ? '<button class="btn ghost" id="prac-an-cancel">✕ 取消</button>' : ''}
    </div>
    ${showLive ? renderResult(activeAnalysis.parsed) : (latest ? renderResult(latest) : '')}
    ${history.length > 0 && !showLive ? `
      <div class="prac-an-history">
        <div class="hdr mono">◇ 历史评估 (${history.length})</div>
        ${[...history].reverse().map((a, idx) => `
          <div class="hist-item" data-an-row="${a.id || idx}">
            <span class="score">${a.score ?? '—'}</span>
            <span class="time">${new Date(a.at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>
            <span class="src">${a.source || ''}</span>
            <button class="hist-del" data-an-del="${a.id || idx}" title="删除这条评估">✕</button>
          </div>
        `).join('')}
      </div>
    ` : ''}
  `;
}

// ─── 追问 (题目级多会话，独立于 variant) ───
function renderFollowupThread(card, q) {
  const host = card.querySelector('#prac-followup-host');
  if (!host) return;

  const sessions = getSessions(q);
  const active = getActiveSession(q);
  const messages = active?.messages || [];
  // 当前查看的 variant 用作 LLM 上下文（可以为 null — 仍然能聊）
  const variant = viewingVariantId ? findVariant(q, viewingVariantId) : null;

  // 顶部 session 选择器
  const sessionBar = `
    <div class="prac-fu-bar">
      <div class="prac-fu-session-select">
        <button class="prac-fu-session-current" data-session-toggle>
          <span class="ic">◆</span>
          <span class="nm">${active ? escapeHtml(active.title || '未命名会话') : '新会话'}</span>
          ${active ? `<span class="cnt mono">${Math.floor(messages.length / 2) || messages.length}</span>` : ''}
          <span class="caret">▾</span>
        </button>
        ${sessionMenuOpen ? `
          <div class="prac-fu-session-menu">
            ${sessions.length === 0
              ? '<div class="empty">还没有会话</div>'
              : sessions.map(s => `
                  <div class="sess-item ${s.id === (active?.id) ? 'active' : ''}" data-switch-session="${escapeHtml(s.id)}">
                    <span class="sess-name">${escapeHtml(s.title || '未命名')}</span>
                    <span class="sess-cnt mono">${Math.floor((s.messages || []).length / 2) || (s.messages || []).length} 轮</span>
                    <button class="sess-rename" data-rename-session="${escapeHtml(s.id)}" title="重命名">✎</button>
                    <button class="sess-del" data-del-session="${escapeHtml(s.id)}" title="删除会话">✕</button>
                  </div>
                `).join('')}
          </div>
        ` : ''}
      </div>
      <button class="prac-fu-new-session" data-new-session title="新建会话">+ 新会话</button>
    </div>
  `;

  // 消息区
  // 上下文提示行 — 告诉用户 LLM 看到了什么。提问独立于答案存在。
  const ctxHint = variant
    ? `<div class="prac-fu-ctx-hint mono">▸ 关于这道题的提问 · LLM 上下文包含「${escapeHtml(variant.template_name)}」答案</div>`
    : `<div class="prac-fu-ctx-hint mono">▸ 关于这道题的提问 · 还没生成 AI 答案，LLM 只看题干</div>`;

  let threadHtml;
  if (messages.length === 0) {
    threadHtml = `
      <div class="prac-fu-empty">
        ${sessions.length === 0
          ? `<div class="hint">关于这道题的第一段提问 — 想深挖什么？</div>`
          : `<div class="hint">这是新会话 — 在下面输入第一个问题</div>`}
        <div class="sub mono">支持流式 · 多会话 · 中文输入法安全</div>
      </div>
    `;
  } else {
    threadHtml = `
      <div class="prac-fu-thread">
        ${messages.map((m, idx) => `
          <div class="prac-fu-msg ${m.role}">
            <div class="msg-head">
              <span class="role">${m.role === 'user' ? '我' : 'AI'}</span>
              <span class="msg-time mono">${m.at ? new Date(m.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''}</span>
              <button class="prac-fu-msg-del" data-fu-del="${idx}" title="${m.role === 'user' ? '删除这一轮（含 AI 回复）' : '只删除这条 AI 回复'}">✕</button>
            </div>
            <div class="msg-content">${escapeHtml(m.content)}</div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // 输入框 — sticky 在底部
  const inputBox = `
    <div class="prac-fu-input-wrap">
      <div class="prac-fu-input">
        <textarea id="prac-fu-text" rows="2" placeholder="${active && messages.length > 0 ? '继续提问 — 换个角度或挖更深' : '开启新会话 — 比如：「Reflector 重连机制是怎么实现的？」'}"></textarea>
        <span class="prac-fu-hint">⏎ 发送 · ⇧⏎ 换行</span>
        <button class="prac-fu-send" id="prac-fu-send">发送 →</button>
      </div>
    </div>
  `;

  host.innerHTML = `
    ${sessionBar}
    ${ctxHint}
    <div class="prac-fu-thread-area">${threadHtml}</div>
    ${inputBox}
  `;

  // 恢复草稿
  const ta = host.querySelector('#prac-fu-text');
  if (ta && followupDraft) {
    ta.value = followupDraft;
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
  }
  // 自动滚到 thread 底部（看到最新消息）
  const threadEl = host.querySelector('.prac-fu-thread-area');
  if (threadEl) threadEl.scrollTop = threadEl.scrollHeight;
}

function bindFollowup(card, q) {
  const host = card.querySelector('#prac-followup-host');
  if (!host) return;

  host.addEventListener('click', async (e) => {
    if (e.target.id === 'prac-fu-send' || e.target.closest('#prac-fu-send')) {
      sendFollowup(card, q);
      return;
    }
    if (e.target.closest('[data-session-toggle]')) {
      sessionMenuOpen = !sessionMenuOpen;
      renderFollowupThread(card, q);
      return;
    }
    const switchEl = e.target.closest('[data-switch-session]');
    if (switchEl && !e.target.closest('.sess-rename, .sess-del')) {
      activeSessionId = switchEl.dataset.switchSession;
      sessionMenuOpen = false;
      followupDraft = '';
      renderFollowupThread(card, q);
      return;
    }
    if (e.target.closest('[data-new-session]')) {
      await createNewSession(card, q);
      return;
    }
    const renameEl = e.target.closest('[data-rename-session]');
    if (renameEl) {
      e.stopPropagation();
      const sid = renameEl.dataset.renameSession;
      const sess = practiceData.sessions.find(s => s.id === sid);
      if (!sess) return;
      const newName = prompt('重命名会话', sess.title || '');
      if (newName == null) return;
      try {
        const updated = await chatApi.patchSession(sid, { title: newName.trim() || '未命名' });
        sess.title = updated.title;
        sess.updated_at = updated.updated_at;
        renderFollowupThread(card, q);
      } catch (e2) { toast('重命名失败：' + e2.message, 'danger'); }
      return;
    }
    const delSessEl = e.target.closest('[data-del-session]');
    if (delSessEl) {
      e.stopPropagation();
      const sid = delSessEl.dataset.delSession;
      const sess = practiceData.sessions.find(s => s.id === sid);
      if (!sess) return;
      try {
        const r = await chatApi.deleteSession(sid);
        const snapshot = r.snapshot;  // 后端返回快照含 messages
        practiceData.sessions = practiceData.sessions.filter(s => s.id !== sid);
        if (activeSessionId === sid) activeSessionId = practiceData.sessions[0]?.id || null;
        renderFollowupThread(card, q);
        undoableToast(`已删除会话「${sess.title || '未命名'}」`, async () => {
          const restored = await chatApi.restoreSession(snapshot);
          practiceData.sessions = [{ ...restored, messages: snapshot.messages || [] }, ...practiceData.sessions];
          activeSessionId = restored.id;
          renderFollowupThread(card, q);
          toast('已恢复', 'success');
        }, { kind: 'success' });
      } catch (e2) { toast('删除失败：' + e2.message, 'danger'); }
      return;
    }
    if (e.target.matches('[data-fu-del]')) {
      e.stopPropagation();
      const idx = parseInt(e.target.dataset.fuDel, 10);
      const sess = getActiveSession(q);
      if (!sess) return;
      const messages = sess.messages || [];
      const msg = messages[idx];
      if (!msg) return;
      // 决定要删的消息：删 user 时同时删后面的 assistant
      let toDelete;
      let label;
      if (msg.role === 'user') {
        toDelete = [msg];
        if (messages[idx + 1]?.role === 'assistant') toDelete.push(messages[idx + 1]);
        label = '已删除一轮对话';
      } else {
        toDelete = [msg];
        label = '已删除 AI 回复';
      }
      try {
        for (const m of toDelete) {
          await chatApi.deleteMessage(m.id);
        }
        sess.messages = messages.filter(m => !toDelete.includes(m));
        renderFollowupThread(card, q);
        // 注意：消息 id 是 SQLite 自增，恢复时 id 会变 — undo 走 addMessage 重建
        undoableToast(label, async () => {
          const restored = [];
          for (const m of toDelete) {
            const r = await chatApi.addMessage(sess.id, m.role, m.content);
            restored.push(r);
          }
          sess.messages = [...sess.messages, ...restored].sort((a, b) => (a.id || 0) - (b.id || 0));
          renderFollowupThread(card, q);
          toast('已恢复', 'success');
        }, { kind: 'success' });
      } catch (e2) {
        toast('删除失败：' + e2.message, 'danger');
      }
      return;
    }
  });

  host.addEventListener('input', (e) => {
    if (e.target.id === 'prac-fu-text') {
      followupDraft = e.target.value;
    }
  });

  host.addEventListener('keydown', (e) => {
    if (
      e.target.id === 'prac-fu-text' &&
      e.key === 'Enter' &&
      !e.shiftKey &&
      !e.isComposing &&
      e.keyCode !== 229
    ) {
      e.preventDefault();
      sendFollowup(card, q);
    }
  });
}

async function createNewSession(card, q) {
  try {
    const created = await chatApi.createSession({
      question_id: q.id,
      title: '新会话',
      variant_ref: viewingVariantId || null,
    });
    practiceData.sessions = [{ ...created, messages: [] }, ...practiceData.sessions];
    activeSessionId = created.id;
    sessionMenuOpen = false;
    followupDraft = '';
    renderFollowupThread(card, q);
    setTimeout(() => {
      const ta = card.querySelector('#prac-fu-text');
      if (ta) ta.focus();
    }, 50);
  } catch (e) {
    toast('创建会话失败：' + e.message, 'danger');
  }
}

async function sendFollowup(card, q) {
  if (activeGen) return;
  const textarea = card.querySelector('#prac-fu-text');
  const content = (textarea?.value || '').trim();
  if (!content) return;

  // 没有 active session 就先建一个
  let sess = getActiveSession(q);
  if (!sess) {
    try {
      const created = await chatApi.createSession({
        question_id: q.id,
        title: autoTitleFromMessage(content),
        variant_ref: viewingVariantId || null,
      });
      sess = { ...created, messages: [] };
      practiceData.sessions = [sess, ...practiceData.sessions];
      activeSessionId = sess.id;
    } catch (e) {
      toast('创建会话失败：' + e.message, 'danger');
      return;
    }
  } else if ((!sess.messages || sess.messages.length === 0) && (!sess.title || sess.title === '新会话')) {
    // 自动改名
    try {
      const updated = await chatApi.patchSession(sess.id, { title: autoTitleFromMessage(content) });
      sess.title = updated.title;
    } catch (_) {}
  }
  if (!Array.isArray(sess.messages)) sess.messages = [];

  // 1. 持久化 user message
  let userMsg;
  try {
    userMsg = await chatApi.addMessage(sess.id, 'user', content);
    sess.messages.push(userMsg);
  } catch (e) {
    toast('保存提问失败：' + e.message, 'danger');
    return;
  }

  textarea.value = '';
  followupDraft = '';
  renderFollowupThread(card, q);

  // 2. 流式生成 assistant 回复
  const variant = viewingVariantId ? findVariant(q, viewingVariantId) : null;
  const llmMessages = [
    {
      role: 'system',
      content: `你是一名资深后端工程师，正在和候选人讨论一道技术面试题。保持口语化、第一人称、有具体例子，不用 markdown，每次回答控制在 3-6 句话以内，自然简洁。${variant ? '\n\n候选人之前对这道题的一份参考答案如下（你可以引用、补充、纠正或完全不提）：\n' + variant.content : ''}`,
    },
    { role: 'user', content: q.text },
    ...sess.messages.map(m => ({ role: m.role, content: m.content })),
  ];

  // 临时占位 assistant 消息（不入库）
  const placeholder = { id: -1, role: 'assistant', content: '', at: new Date().toISOString() };
  sess.messages.push(placeholder);
  renderFollowupThread(card, q);

  let fullText = '';
  const handle = llmApi.chatStream(llmMessages, {
    temperature: 0.6,
    onDelta: (_, full) => {
      fullText = full;
      placeholder.content = full;
      const contentEls = card.querySelectorAll('.prac-fu-msg.assistant .msg-content');
      const lastEl = contentEls[contentEls.length - 1];
      if (lastEl) lastEl.textContent = full;
    },
  });
  activeGen = { abort: handle.abort, timer: null };

  try {
    await handle.promise;
    activeGen = null;
    // 3. 持久化 assistant message —— 替换占位
    sess.messages.pop();
    if (fullText.trim()) {
      const aiMsg = await chatApi.addMessage(sess.id, 'assistant', fullText);
      sess.messages.push(aiMsg);
    }
    renderFollowupThread(card, q);
  } catch (e) {
    activeGen = null;
    sess.messages.pop();  // 移除占位
    if (e.name !== 'AbortError') {
      toast('提问失败：' + e.message, 'danger');
    }
    renderFollowupThread(card, q);
  }
}

// ─── 评估绑定 ───
function bindAnalyze(card, q) {
  const host = card.querySelector('#prac-followup-host');
  if (!host || followupMode !== 'analyze') return;

  host.addEventListener('click', async (e) => {
    if (e.target.matches('[data-src]')) {
      analysisSource = e.target.dataset.src;
      analysisDraft = '';  // 切来源时清草稿，让默认值重新填
      renderAnalyzePane(card, q);
      bindAnalyze(card, q);  // 重绑（host innerHTML 重置了）
    } else if (e.target.id === 'prac-an-run') {
      runAnalysis(card, q);
    } else if (e.target.id === 'prac-an-cancel') {
      if (activeAnalysis?.abort) activeAnalysis.abort();
    } else if (e.target.closest('[data-rel-q]')) {
      // 跳转到相关弱项题：替换当前 session 的当前题
      const btn = e.target.closest('[data-rel-q]');
      const id = btn.dataset.relQ;
      const allQs = questionsStore.state.questions;
      const idx = allQs.findIndex(qq => qq.id === id);
      if (idx >= 0) {
        session.queue = allQs;
        viewingVariantId = null;
        followupMode = 'chat';
        editingVariant = false;
        gotoIndex(idx);
      }
    } else if (e.target.matches('[data-an-del]')) {
      const id = e.target.dataset.anDel;
      const target = practiceData.analyses.find(a => a.id === id);
      if (!target) return;
      try {
        const r = await analysesApi.delete(id);
        const snapshot = r.snapshot;
        practiceData.analyses = practiceData.analyses.filter(a => a.id !== id);
        renderAnalyzePane(card, q);
        bindAnalyze(card, q);
        undoableToast(`已删除评估 (${snapshot.score ?? '—'} 分)`, async () => {
          const restored = await analysesApi.restore(snapshot);
          practiceData.analyses = [...practiceData.analyses, restored]
            .sort((a, b) => (a.at || '').localeCompare(b.at || ''));
          renderAnalyzePane(card, q);
          bindAnalyze(card, q);
          toast('已恢复', 'success');
        }, { kind: 'success' });
      } catch (e2) {
        toast('删除失败：' + e2.message, 'danger');
      }
    }
  });
  host.addEventListener('input', (e) => {
    if (e.target.id === 'prac-an-text') {
      analysisDraft = e.target.value;
    }
  });
}

async function runAnalysis(card, q) {
  if (activeAnalysis) return;
  const ta = card.querySelector('#prac-an-text');
  const userText = (ta?.value || '').trim();
  if (!userText) {
    toast('需要先写/粘贴你的回答', 'danger');
    return;
  }
  const variant = viewingVariantId ? findVariant(q, viewingVariantId) : null;

  activeAnalysis = { partial: '', parsed: parseAnalysis(''), abort: null };
  renderAnalyzePane(card, q);
  bindAnalyze(card, q);

  const handle = analysesApi.stream({
    question_id: q.id,
    user_text: userText,
    source: analysisSource,
    against_answer_id: variant?.id || null,
  }, {
    onDelta: (_, full) => {
      if (!activeAnalysis) return;
      activeAnalysis.partial = full;
      activeAnalysis.parsed = parseAnalysis(full);
      renderAnalyzePane(card, q);
      bindAnalyze(card, q);
    },
  });
  activeAnalysis.abort = handle.abort;

  try {
    const full = await handle.promise;
    const parsed = parseAnalysis(full);
    if (parsed.score == null && parsed.strengths.length === 0 && parsed.gaps.length === 0) {
      toast('分析没返回有效结构 — 看一下原始输出', 'danger');
      activeAnalysis = null;
      renderAnalyzePane(card, q);
      bindAnalyze(card, q);
      return;
    }
    // 持久化 —— dedicated analyses API
    const created = await analysesApi.create({
      question_id: q.id,
      user_text: userText,
      source: analysisSource,
      against_answer_id: variant?.id || null,
      score: parsed.score,
      strengths: parsed.strengths,
      gaps: parsed.gaps,
      suggestions: parsed.suggestions,
      topics_touched: parsed.topics_touched,
    });
    practiceData.analyses = [...practiceData.analyses, created];
    toast(`评估完成 · ${parsed.score}/100`, 'success');
    activeAnalysis = null;
    analysisDraft = '';
    renderAnalyzePane(card, q);
    bindAnalyze(card, q);
  } catch (e) {
    activeAnalysis = null;
    if (e.name !== 'AbortError') toast('分析失败：' + e.message, 'danger');
    renderAnalyzePane(card, q);
    bindAnalyze(card, q);
  }
}

// ─── 笔记（防抖自动保存） ───
function bindNote(card, q) {
  const ta = card.querySelector('#prac-note');
  const stateEl = card.querySelector('#prac-note-state');
  if (!ta) return;

  let timer = null;
  const save = async () => {
    const note = ta.value;
    if (note === (q.note || '')) return;
    if (stateEl) stateEl.textContent = '⋯ 保存中';
    try {
      await questionsApi.patch(q.id, { note });
      q.note = note;
      if (stateEl) {
        stateEl.textContent = '✓ 已保存';
        setTimeout(() => { if (stateEl) stateEl.textContent = ''; }, 1500);
      }
    } catch (e) {
      if (stateEl) stateEl.textContent = '✕ ' + e.message;
    }
  };

  ta.addEventListener('input', () => {
    if (timer) clearTimeout(timer);
    if (stateEl) stateEl.textContent = '✎ 编辑中';
    timer = setTimeout(save, 800);
  });
  ta.addEventListener('blur', () => {
    if (timer) { clearTimeout(timer); timer = null; }
    save();
  });
}

// ─── streaming AI 生成 ───
function startGeneration(card, q, templateId) {
  if (activeGen) return;
  const tpl = getTemplateById(templateId || lastTemplateId);
  lastTemplateId = tpl.id;

  const host = card.querySelector('#prac-answer-host');
  host.innerHTML = `
    <div class="prac-tpl-tag mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px">▸ ${escapeHtml(tpl.name)}</div>
    <div class="prac-answer" id="prac-stream"></div>
    <div style="margin-top:10px;display:flex;align-items:center;gap:10px">
      <button class="btn" id="prac-cancel">✕ 取消</button>
      <span class="mono" id="prac-elapsed" style="font-size:10px;color:var(--char-soft);letter-spacing:0.06em">⋯ 生成中 0s</span>
      <span class="mono" id="prac-chars" style="font-size:10px;color:var(--char-soft);margin-left:auto">0 chars</span>
    </div>
  `;
  const liveEl = host.querySelector('#prac-stream');
  const elapsedEl = host.querySelector('#prac-elapsed');
  const charsEl = host.querySelector('#prac-chars');
  const startTs = Date.now();
  const timer = setInterval(() => {
    if (elapsedEl) elapsedEl.textContent = `⋯ 生成中 ${Math.floor((Date.now() - startTs) / 1000)}s`;
  }, 500);

  const handle = llmApi.chatStream(
    [
      { role: 'system', content: tpl.content },
      { role: 'user', content: q.text },
    ],
    {
      temperature: 0.65,
      onDelta: (_, full) => {
        liveEl.textContent = full;
        if (charsEl) charsEl.textContent = `${full.length} chars`;
      },
    },
  );
  activeGen = { abort: handle.abort, timer };

  host.querySelector('#prac-cancel').addEventListener('click', () => {
    try { handle.abort(); } catch (_) {}
  });

  handle.promise.then(async (full) => {
    clearInterval(timer);
    activeGen = null;
    if (!full || !full.trim()) {
      toast('LLM 没返回内容', 'danger');
      session.revealed = true;
      renderCard();
      return;
    }
    try {
      // upsert 这个 template 的 Answer
      const created = await answersApi.create({
        question_id: q.id,
        template_id: tpl.id,
        template_name: tpl.name,
        content: full,
      });
      // 更新本地缓存
      practiceData.answers = practiceData.answers
        .filter(a => a.template_id !== tpl.id)
        .concat([created]);
      // 同步 question.answer 主答案字段
      await questionsApi.patch(q.id, { answer: full });
      q.answer = full;
      viewingVariantId = tpl.id;
      session.revealed = true;
      renderCard();
    } catch (e) { toast('保存失败：' + e.message, 'danger'); }
  }).catch((e) => {
    clearInterval(timer);
    activeGen = null;
    if (e.name === 'AbortError') {
      toast('已取消生成', 'success');
      session.revealed = false;
      renderCard();
      return;
    }
    toast('生成失败：' + e.message, 'danger');
    session.revealed = false;
    renderCard();
  });
}

function abortGenIfRunning() {
  if (activeGen) {
    try { activeGen.abort(); } catch (_) {}
    clearInterval(activeGen.timer);
    activeGen = null;
  }
}

// ─── ASR ───
function bindAsrControls(card, q) {
  const btn = card.querySelector('#prac-mic');
  const stateEl = card.querySelector('#prac-mic-state');
  const liveEl = card.querySelector('#prac-live');
  const saveBtn = card.querySelector('#prac-mic-save');

  if (liveTranscript) {
    liveEl.textContent = liveTranscript;
    saveBtn.style.display = 'inline-flex';
  }

  const setS = (s) => { stateEl.textContent = s; };

  btn.addEventListener('click', async () => {
    if (asrClient && (asrClient.state === 'recording' || asrClient.state === 'requesting-mic' || asrClient.state === 'connecting')) {
      // stop
      btn.textContent = '⋯ 停止中';
      try { await asrClient.stop(); } catch (_) {}
      btn.textContent = '🎙 重新开始';
      liveEl.classList.remove('active');
      if (liveTranscript) saveBtn.style.display = 'inline-flex';
      asrClient = null;
      return;
    }

    const asrCfg = settingsStore.state.asr;
    if (!asrCfg || !asrCfg.wsUrl || !asrCfg.apiAppId) {
      toast('请先在右上 ⚙ → ASR 配置火山引擎', 'danger');
      return;
    }

    liveTranscript = '';
    liveEl.textContent = '';
    saveBtn.style.display = 'none';
    liveEl.classList.add('active');

    asrClient = new ASRClient({
      wsUrl: `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/asr/ws`,
      config: asrCfg,
      onState: setS,
      onPartial: (t) => { liveTranscript = t; liveEl.textContent = t; },
      onFinal:   (t) => { liveTranscript = t; liveEl.textContent = t; },
      onError:   (e) => { toast('ASR: ' + e.message, 'danger'); },
    });

    btn.textContent = '⋯ 启动中';
    try {
      await asrClient.start();
      btn.textContent = '⏹ 停止口述';
    } catch (e) {
      toast(e.message, 'danger');
      btn.textContent = '🎙 开始口述';
      liveEl.classList.remove('active');
      asrClient = null;
    }
  });

  saveBtn.addEventListener('click', async () => {
    if (!liveTranscript) return;
    try {
      const logs = (q.speaking_logs || []).slice();
      logs.push({
        text: liveTranscript,
        at: new Date().toISOString(),
      });
      await questionsApi.patch(q.id, { speaking_logs: logs });
      q.speaking_logs = logs;
      toast('已保存到 speaking_logs', 'success');
      saveBtn.style.display = 'none';
      liveTranscript = '';
    } catch (e) { toast(e.message, 'danger'); }
  });
}

async function stopAsrIfRunning() {
  if (asrClient && asrClient.state !== 'idle' && asrClient.state !== 'closed') {
    try { await asrClient.stop(); } catch (_) {}
  }
  asrClient = null;
  liveTranscript = '';
  abortGenIfRunning();
}
