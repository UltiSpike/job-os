import { openModal, closeModal } from '../components/modal.js';
import { addInterview, jobsStore, setState, reloadInterviews } from '../store/jobs.js';
import { interviewsApi } from '../api/interviews.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';
import { escapeHtml } from '../components/html.js';
import { refreshMastery } from '../store/me.js';

const TYPES = ['HR 沟通', '一面', '二面', '三面', 'Onsite', 'HR 终面'];
const RESULT_LABEL = { pending: '待定', pass: '通过', fail: '挂了' };

function toLocalDatetime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  // datetime-local 需要 YYYY-MM-DDTHH:MM
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function buildBody(iv) {
  return `
    <div class="field">
      <label>类型</label>
      <select id="iv-type">
        ${TYPES.map(t => `<option ${iv.type === t ? 'selected' : ''}>${t}</option>`).join('')}
      </select>
    </div>
    <div class="field">
      <label>时间</label>
      <input id="iv-time" type="datetime-local" value="${toLocalDatetime(iv.time)}">
    </div>
    <div class="field">
      <label>地点 / 链接</label>
      <input id="iv-loc" type="text" value="${escapeHtml(iv.location || '')}" placeholder="腾讯会议 / 现场地址">
    </div>
    <div class="field">
      <label>结果</label>
      <select id="iv-result">
        ${['pending', 'pass', 'fail'].map(r => `<option value="${r}" ${iv.result === r ? 'selected' : ''}>${RESULT_LABEL[r]}</option>`).join('')}
      </select>
    </div>
    <div class="field">
      <label>反思 (可后补)</label>
      <textarea id="iv-ref" rows="4" placeholder="你怎么答的，对方反馈如何">${escapeHtml(iv.reflection || '')}</textarea>
    </div>
  `;
}

function readForm(card) {
  const time = card.querySelector('#iv-time').value;
  return {
    type: card.querySelector('#iv-type').value,
    time: time ? new Date(time).toISOString() : null,
    location: card.querySelector('#iv-loc').value,
    result: card.querySelector('#iv-result').value,
    reflection: card.querySelector('#iv-ref').value,
  };
}

const STAGE_LABELS = {
  todo: '待投', applied: '已投', contacting: '联系中',
  interviewing: '面试中', offer: 'Offer', closed: '已结案',
};

// 新建面试
export function openInterviewModal(jobId, defaults = {}) {
  openModal({
    title: '记录面试',
    sub: '新建面试记录',
    body: buildBody({ result: 'pending', ...defaults }),
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="iv-save">保存</button>
    `,
    onMount(card) {
      card.querySelector('#iv-save').addEventListener('click', async () => {
        try {
          const created = await addInterview(jobId, readForm(card));
          closeModal();
          router.refresh();
          // 自动推进 stage 时给 undoable toast
          if (created && created._auto_advanced_from) {
            const fromCol = created._auto_advanced_from;
            undoableToast(
              `已自动推进到「${STAGE_LABELS.interviewing}」(从「${STAGE_LABELS[fromCol]}」)`,
              async () => {
                await setState(jobId, { pipeline_col: fromCol });
                router.refresh();
                toast(`已回退到「${STAGE_LABELS[fromCol]}」`, 'success');
              },
              { kind: 'success', timeout: 6000 }
            );
          } else {
            toast('面试已记录', 'success');
          }
        } catch (e) {
          toast('保存失败：' + e.message, 'danger');
        }
      });
    },
  });
}

// ─── Verification 闭环：记录这次面试涉及的 concepts ───
const OUTCOME_LABEL = { good: '✓ 答得好', ok: '◐ 一般', bad: '○ 翻车', unknown: '— 未知' };
const DEPTH_LABEL = { 1: '浅', 2: '中', 3: '深' };

function buildConceptsSection() {
  return `
    <div class="iv-concepts-sec">
      <div class="iv-concepts-head">
        <span class="iv-concepts-title">◇ 涉及的知识点（mastery 反馈用）</span>
      </div>
      <div class="iv-concepts-list" id="iv-concepts-list">
        <div class="iv-concepts-empty mono">载入中…</div>
      </div>
      <div class="iv-concepts-extract">
        <textarea id="iv-concepts-notes" rows="3" placeholder="粘贴你的面试笔记，AI 会自动识别涉及的 concepts + 估算表现"></textarea>
        <div class="iv-concepts-actions">
          <button class="btn ghost" type="button" id="iv-concepts-extract-btn">✦ 让 AI 抽取</button>
          <span class="iv-concepts-status mono" id="iv-concepts-status"></span>
        </div>
      </div>
    </div>
  `;
}

async function loadInterviewConcepts(card, interviewId) {
  const list = card.querySelector('#iv-concepts-list');
  if (!list) return;
  try {
    const r = await interviewsApi.listConcepts(interviewId);
    renderConceptsList(card, interviewId, r.items || []);
  } catch (e) {
    list.innerHTML = `<div class="iv-concepts-empty mono">载入失败：${escapeHtml(e.message)}</div>`;
  }
}

function renderConceptsList(card, interviewId, items) {
  const list = card.querySelector('#iv-concepts-list');
  if (!list) return;
  if (items.length === 0) {
    list.innerHTML = '<div class="iv-concepts-empty mono">还没记录涉及的 concept — 用下方 LLM 抽取或手动添加</div>';
    return;
  }
  list.innerHTML = items.map(it => `
    <div class="iv-concept-row">
      <span class="iv-concept-name">${escapeHtml(it.concept_name || it.concept_slug)}</span>
      <span class="iv-concept-depth">深度 ${DEPTH_LABEL[it.asked_depth] || it.asked_depth}</span>
      <span class="iv-concept-outcome r-${it.outcome}">${OUTCOME_LABEL[it.outcome] || it.outcome}</span>
      <button class="iv-concept-del" data-del-concept="${it.id}" title="移除">✕</button>
    </div>
  `).join('');
  card.querySelectorAll('[data-del-concept]').forEach(el => {
    el.addEventListener('click', async () => {
      try {
        await interviewsApi.deleteConcept(el.dataset.delConcept);
        await loadInterviewConcepts(card, interviewId);
        refreshMastery();
      } catch (e) { toast(e.message, 'danger'); }
    });
  });
}

function bindConceptsSection(card, interviewId) {
  const btn = card.querySelector('#iv-concepts-extract-btn');
  const status = card.querySelector('#iv-concepts-status');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const notes = card.querySelector('#iv-concepts-notes')?.value || '';
    if (!notes.trim()) {
      toast('先粘贴笔记', 'danger');
      return;
    }
    btn.disabled = true;
    if (status) status.textContent = '⋯ AI 抽取中';
    try {
      const r = await interviewsApi.extractConcepts(interviewId, notes);
      const items = r.items || [];
      if (items.length === 0) {
        if (status) status.textContent = '没匹配到 concept';
        return;
      }
      // 自动 insert 所有抽取出来的 concept
      let inserted = 0;
      for (const it of items) {
        try {
          await interviewsApi.addConcept(interviewId, {
            concept_slug: it.concept_slug,
            asked_depth: it.asked_depth,
            outcome: it.outcome,
            note: it.evidence || '',
          });
          inserted++;
        } catch (_) {}
      }
      await loadInterviewConcepts(card, interviewId);
      refreshMastery();
      if (status) status.textContent = `✓ 已写入 ${inserted} / ${items.length}`;
      toast(`AI 识别 ${items.length} 个 concept`, 'success');
    } catch (e) {
      if (status) status.textContent = '✕ ' + e.message;
      toast('抽取失败：' + e.message, 'danger');
    } finally {
      btn.disabled = false;
    }
  });
}

// 编辑已有面试
export function openInterviewEditModal(interview, onAfter) {
  openModal({
    title: '编辑面试',
    sub: `${interview.type} · #${interview.id}`,
    body: buildBody(interview) + buildConceptsSection(),
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="iv-save">保存</button>
    `,
    onMount(card) {
      // 加载已记录的 concepts
      loadInterviewConcepts(card, interview.id);
      bindConceptsSection(card, interview.id);

      card.querySelector('#iv-save').addEventListener('click', async () => {
        try {
          const newData = readForm(card);
          const oldResult = interview.result || 'pending';
          await interviewsApi.patch(interview.id, newData);
          await reloadInterviews();
          toast('已保存', 'success');
          closeModal();
          if (onAfter) onAfter();
          router.refresh();
          // result 改成 fail → 一个 toast 询问是否移到已结案
          if (newData.result === 'fail' && oldResult !== 'fail') {
            const jobId = interview.job_id;
            const curState = jobsStore.state.states[jobId];
            if (curState && !['closed', 'offer'].includes(curState.pipeline_col)) {
              undoableToast(
                `「${interview.type}」挂了 — 是否移到「已结案」？`,
                async () => {
                  await setState(jobId, { pipeline_col: 'closed' });
                  router.refresh();
                  toast('已移到已结案', 'success');
                },
                { kind: 'danger', timeout: 7000, actionLabel: '移到结案' }
              );
            }
          }
        } catch (e) {
          toast('保存失败：' + e.message, 'danger');
        }
      });
    },
  });
}
