// Cmd+K 全局命令面板 — 跳页 / 搜题 / 快速操作
import { router } from '../app.js';
import { jobsStore } from '../store/jobs.js';
import { questionsStore } from '../store/questions.js';
import { setPipelineFilter, clearPipelineFilter } from '../views/pipeline.js';
import { escapeHtml } from './html.js';
import { cleanTitle, clean } from './text.js';

let isOpen = false;
let query = '';
let selectedIdx = 0;

const STATIC_COMMANDS = [
  { id: 'goto-today',     label: '跳到 Today',          hint: '导航', action: () => router.go('today') },
  { id: 'goto-discover',  label: '跳到 Discover',       hint: '导航', action: () => router.go('discover') },
  { id: 'goto-pipeline',  label: '跳到 Pipeline',       hint: '导航', action: () => router.go('pipeline') },
  { id: 'goto-training',  label: '跳到 Training',       hint: '导航', action: () => router.go('training') },
  { id: 'goto-decision',  label: '跳到 Decision',       hint: '导航', action: () => router.go('decision') },
  { id: 'pl-target',  label: '查看目标岗位',          hint: 'Pipeline 过滤', action: () => { setPipelineFilter({ label: '意图：目标', intents: ['target'] }); router.go('pipeline'); } },
  { id: 'pl-iving',   label: '查看面试中 / Offer',     hint: 'Pipeline 过滤', action: () => { setPipelineFilter({ label: '面试中 / Offer', cols: ['interviewing', 'offer'] }); router.go('pipeline'); } },
  { id: 'pl-pending', label: '查看待回应（已投/联系中）', hint: 'Pipeline 过滤', action: () => { setPipelineFilter({ label: '待回应', cols: ['applied', 'contacting'] }); router.go('pipeline'); } },
  { id: 'pl-stuck',   label: '查看停滞 ≥7 天的卡片',   hint: 'Pipeline 过滤', action: () => { setPipelineFilter({ label: '停滞 ≥7 天', cols: ['applied', 'contacting', 'interviewing'], minStuckDays: 7 }); router.go('pipeline'); } },
  { id: 'pl-clear',   label: '清除 Pipeline 过滤',     hint: '动作', action: () => { clearPipelineFilter(); router.go('pipeline'); } },
];

function getCommands(q) {
  const queryLower = (q || '').toLowerCase().trim();
  const all = [];

  // 静态命令
  for (const c of STATIC_COMMANDS) {
    if (!queryLower || c.label.toLowerCase().includes(queryLower) || c.hint.toLowerCase().includes(queryLower)) {
      all.push({ ...c, kind: 'cmd' });
    }
  }

  if (queryLower.length >= 2) {
    // 题库搜索
    const qs = (questionsStore.state.questions || []);
    for (const q of qs) {
      if (q.text.toLowerCase().includes(queryLower) || (q.topics || []).some(t => t.toLowerCase().includes(queryLower))) {
        all.push({
          id: 'q:' + q.id,
          kind: 'question',
          label: q.text.slice(0, 60),
          hint: '题目 · ' + ((q.topics || []).slice(0, 2).join(', ') || '无标签'),
          action: () => {
            // 导航到 training 并触发该题练习
            window.__pendingPracticeQuestionId = q.id;
            router.go('training');
          },
        });
        if (all.length > 30) break;
      }
    }
    // 岗位搜索
    const jobs = jobsStore.state.jobs || [];
    let added = 0;
    for (const job of jobs) {
      const title = (job.title || '').toLowerCase();
      const company = (job.company || '').toLowerCase();
      if (title.includes(queryLower) || company.includes(queryLower)) {
        all.push({
          id: 'j:' + job.href,
          kind: 'job',
          label: cleanTitle(job.title).slice(0, 60),
          hint: '岗位 · ' + clean(job.company),
          action: () => {
            // 跳 pipeline 并 search 这个公司
            router.go('pipeline');
          },
        });
        added++;
        if (added > 8) break;
      }
    }
  }

  return all.slice(0, 40);
}

function render() {
  const commands = getCommands(query);
  if (selectedIdx >= commands.length) selectedIdx = Math.max(0, commands.length - 1);

  const host = document.getElementById('cmdk-host');
  if (!host) return;

  host.innerHTML = `
    <div class="cmdk-overlay" data-cmdk-close></div>
    <div class="cmdk-card">
      <div class="cmdk-input-wrap">
        <span class="cmdk-prompt mono">⌕</span>
        <input id="cmdk-input" type="text" value="${escapeHtml(query)}" placeholder="跳页 / 搜题 / 搜岗位 / 命令…" autocomplete="off">
        <span class="cmdk-hint mono">esc 关闭 · ↑↓ 选择 · ⏎ 执行</span>
      </div>
      <div class="cmdk-list" id="cmdk-list">
        ${commands.length === 0
          ? '<div class="cmdk-empty">没有匹配的命令</div>'
          : commands.map((c, i) => `
            <div class="cmdk-item ${i === selectedIdx ? 'sel' : ''}" data-idx="${i}">
              <span class="cmdk-kind cmdk-kind-${c.kind}">${c.kind === 'cmd' ? '▸' : c.kind === 'question' ? '◇' : '◆'}</span>
              <span class="cmdk-label">${escapeHtml(c.label)}</span>
              <span class="cmdk-hint">${escapeHtml(c.hint || '')}</span>
            </div>
          `).join('')}
      </div>
    </div>
  `;

  const input = host.querySelector('#cmdk-input');
  if (input) {
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }
}

function open() {
  if (isOpen) return;
  isOpen = true;
  query = '';
  selectedIdx = 0;
  let host = document.getElementById('cmdk-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'cmdk-host';
    host.className = 'cmdk-host';
    document.body.appendChild(host);
  }
  host.style.display = 'block';
  render();
  document.addEventListener('keydown', onKey);
  host.addEventListener('click', onClick);
  host.addEventListener('input', onInput);
}

function close() {
  if (!isOpen) return;
  isOpen = false;
  const host = document.getElementById('cmdk-host');
  if (host) {
    host.style.display = 'none';
    host.innerHTML = '';
  }
  document.removeEventListener('keydown', onKey);
}

function onKey(e) {
  if (!isOpen) return;
  if (e.key === 'Escape') { e.preventDefault(); close(); return; }
  const commands = getCommands(query);
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIdx = Math.min(commands.length - 1, selectedIdx + 1);
    render();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIdx = Math.max(0, selectedIdx - 1);
    render();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    const c = commands[selectedIdx];
    if (c) { close(); c.action(); }
  }
}

function onClick(e) {
  if (e.target.matches('[data-cmdk-close]')) { close(); return; }
  const item = e.target.closest('.cmdk-item');
  if (item) {
    const idx = parseInt(item.dataset.idx, 10);
    const commands = getCommands(query);
    const c = commands[idx];
    if (c) { close(); c.action(); }
  }
}

function onInput(e) {
  if (e.target.id === 'cmdk-input') {
    query = e.target.value;
    selectedIdx = 0;
    render();
  }
}

// 注册全局快捷键 Cmd+K / Ctrl+K
export function installCommandPalette() {
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (isOpen) close();
      else open();
    }
  });
}

export { open as openCommandPalette, close as closeCommandPalette };
