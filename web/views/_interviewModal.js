import { openModal, closeModal } from '../components/modal.js';
import { addInterview, jobsStore, setState, reloadInterviews } from '../store/jobs.js';
import { interviewsApi } from '../api/interviews.js';
import { toast, undoableToast } from '../components/toast.js';
import { router } from '../app.js';
import { escapeHtml } from '../components/html.js';

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

// 编辑已有面试
export function openInterviewEditModal(interview, onAfter) {
  openModal({
    title: '编辑面试',
    sub: `${interview.type} · #${interview.id}`,
    body: buildBody(interview),
    actions: `
      <button class="btn" data-close>取消</button>
      <button class="btn primary" id="iv-save">保存</button>
    `,
    onMount(card) {
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
