import { openModal, closeModal } from '../components/modal.js';
import { llmApi } from '../api/llm.js';
import { llmPresetsApi } from '../api/llmPresets.js';
import { settingsApi, resumesApi } from '../api/settings.js';
import { resumeProfilesApi } from '../api/curriculum.js';
import { asrConfigApi } from '../api/asrConfig.js';
import { promptTemplatesApi } from '../api/promptTemplates.js';
import { profileApi } from '../api/profile.js';
import { settingsStore, loadSettings } from '../store/settings.js';
import { toast, undoableToast } from '../components/toast.js';
import { escapeHtml } from '../components/html.js';

const TABS = [
  { id: 'llm',     label: 'LLM' },
  { id: 'asr',     label: 'ASR' },
  { id: 'profile', label: 'Profile' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'resumes', label: '简历' },
];

let currentTab = 'llm';
let editingPreset = null;  // currently edited preset name (null = new)
let editingPromptId = null; // 编辑中的 prompt id
let editingResumeId = null; // 编辑中的简历 id（'new' = 新建）
let editingResumeDraft = { name: '', content: '', is_default: false };
let resumeProfiles = {}; // resumeId -> latest profile (or null)
let extractingResumeId = null;

export async function openSettingsModal() {
  if (!settingsStore.state.loaded) {
    try { await loadSettings(); }
    catch (e) { toast(e.message, 'danger'); }
  }
  renderModal();
}

function renderModal() {
  const css = `
    <style>
      .stab-bar { display:flex; border-bottom:1px solid var(--line-paper-2); margin: -8px -40px 24px; }
      .stab-bar button {
        font-family: var(--font-mono); font-size: 10px; text-transform: uppercase;
        letter-spacing: 0.12em; padding: 14px 22px; color: var(--char-soft);
        border-bottom: 2px solid transparent; margin-bottom: -1px;
      }
      .stab-bar button:hover { color: var(--char); }
      .stab-bar button.active { color: var(--amber-soft); border-bottom-color: var(--amber); }
      .preset-list { display:flex; flex-direction:column; margin-bottom: 18px; }
      .preset-row {
        display:grid; grid-template-columns: auto 1fr auto auto; gap: 12px;
        align-items: center; padding: 10px 0; border-bottom: 1px dashed var(--line-paper-2);
        font-family: var(--font-mono); font-size: 11px; color: var(--char-soft);
      }
      .preset-row .nm { color: var(--char); font-weight: 500; }
      .preset-row.active { color: var(--amber-soft); }
      .preset-row.active .dot { color: var(--amber); }
      .preset-row .dot { color: var(--char-soft); }
      .preset-row button { padding: 4px 10px; font-size: 9px; border:1px solid var(--line-paper-2); color: var(--char-soft); text-transform:uppercase; letter-spacing:0.08em; }
      .preset-row button:hover { color: var(--amber-soft); border-color: var(--amber); }
      .preset-row button.del:hover { color: var(--rust); border-color: var(--rust); }
      .empty-line { font-family: var(--font-mono); font-size:10px; color: var(--char-soft); padding: 6px 0; font-style: italic; }
      .ll-result { font-family: var(--font-mono); font-size: 11px; color: var(--char-soft); min-height: 18px; margin-top: 8px; }
    </style>
  `;
  openModal({
    title: '配置',
    sub: 'Settings · 全部存于 SQLite',
    body: css + `
      <div class="stab-bar">
        ${TABS.map(t => `<button data-stab="${t.id}" class="${currentTab === t.id ? 'active' : ''}">${t.label}</button>`).join('')}
      </div>
      <div id="stab-body">${renderTab()}</div>
    `,
    actions: '',
    onMount(card) {
      bindCommon(card);
      bindTab(card);
    },
  });
}

function renderTab() {
  switch (currentTab) {
    case 'llm':     return renderLLMTab();
    case 'asr':     return renderASRTab();
    case 'profile': return renderProfileTab();
    case 'prompts': return renderPromptsTab();
    case 'resumes': return renderResumesTab();
  }
  return '';
}

function bindCommon(card) {
  card.querySelectorAll('[data-stab]').forEach(el => {
    el.addEventListener('click', () => {
      currentTab = el.dataset.stab;
      editingPreset = null;
      renderModal();
    });
  });
}

function bindTab(card) {
  switch (currentTab) {
    case 'llm':     return bindLLMTab(card);
    case 'asr':     return bindASRTab(card);
    case 'profile': return bindProfileTab(card);
    case 'prompts': return bindPromptsTab(card);
    case 'resumes': return bindResumesTab(card);
  }
}

// ─── LLM tab ─────────────────────────────────
function renderLLMTab() {
  const { llmPresets, llmActive } = settingsStore.state;
  const editing = editingPreset !== null
    ? (llmPresets.find(p => p.name === editingPreset) || { name: '', base_url: '', model: '', api_key: '', extra_headers: '' })
    : null;

  const list = llmPresets.length === 0
    ? '<div class="empty-line">暂无 preset — 在下方添加</div>'
    : llmPresets.map(p => `
        <div class="preset-row ${p.name === llmActive ? 'active' : ''}">
          <span class="dot">●</span>
          <span class="nm">${escapeHtml(p.name)} <span style="color:var(--char-soft);font-weight:400">${escapeHtml(p.model || '')}</span></span>
          <button data-act-preset="${escapeHtml(p.name)}">${p.name === llmActive ? '已激活' : '激活'}</button>
          <span style="display:flex;gap:4px">
            <button data-edit-preset="${escapeHtml(p.name)}">改</button>
            <button class="del" data-del-preset="${escapeHtml(p.name)}">删</button>
          </span>
        </div>
      `).join('');

  return `
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ Presets</div>
    <div class="preset-list">${list}</div>

    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin: 22px 0 10px">
      ${editing ? (editingPreset ? '◇ 编辑 ' + escapeHtml(editingPreset) : '◇ 新建 preset') : '◇ 新建 preset'}
    </div>
    <div class="field"><label>名称</label><input id="ll-name" type="text" value="${escapeHtml(editing?.name || '')}" placeholder="dev / openai / volc"></div>
    <div class="field"><label>Base URL</label><input id="ll-base" type="text" value="${escapeHtml(editing?.base_url || '')}" placeholder="https://api.openai.com/v1"></div>
    <div class="field"><label>Model</label><input id="ll-model" type="text" value="${escapeHtml(editing?.model || '')}" placeholder="gpt-4o-mini"></div>
    <div class="field"><label>API Key ${editing?.api_key_masked ? `<span style="color:var(--char-soft)">已存：${editing.api_key_masked}</span>` : ''}</label><input id="ll-key" type="password" placeholder="sk-..."></div>
    <div class="field"><label>Extra Headers (一行一个 k: v)</label><textarea id="ll-extra" placeholder="X-Custom: value">${escapeHtml(editing?.extra_headers || '')}</textarea></div>

    <div class="ll-result" id="ll-result"></div>

    <div class="actions">
      ${editing && editingPreset ? '<button class="btn" id="ll-cancel">取消</button>' : ''}
      <button class="btn" id="ll-test">测试</button>
      <button class="btn primary" id="ll-save">${editingPreset ? '保存修改' : '添加 preset'}</button>
    </div>
  `;
}

function bindLLMTab(card) {
  const get = () => ({
    name: card.querySelector('#ll-name').value.trim(),
    base_url: card.querySelector('#ll-base').value.trim(),
    model: card.querySelector('#ll-model').value.trim(),
    api_key: card.querySelector('#ll-key').value.trim(),
    extra_headers: card.querySelector('#ll-extra').value,
  });
  const result = card.querySelector('#ll-result');

  card.querySelector('#ll-test')?.addEventListener('click', async () => {
    result.textContent = '⋯ testing';
    try {
      const r = await llmApi.test({ target: get() });
      result.innerHTML = r.ok
        ? `<span style="color:var(--sage)">✓ ${escapeHtml(r.answer || 'ok')}</span>`
        : `<span style="color:var(--rust)">✕ ${escapeHtml(r.error || String(r.status))}</span>`;
    } catch (e) {
      result.innerHTML = `<span style="color:var(--rust)">✕ ${escapeHtml(e.message)}</span>`;
    }
  });

  card.querySelector('#ll-save')?.addEventListener('click', async () => {
    const data = get();
    if (!data.name || !data.base_url || !data.model) {
      toast('name / base_url / model 必填', 'danger');
      return;
    }
    try {
      await llmPresetsApi.upsert(data);
      await loadSettings();
      editingPreset = null;
      toast('已保存', 'success');
      renderModal();
    } catch (e) { toast(e.message, 'danger'); }
  });

  card.querySelector('#ll-cancel')?.addEventListener('click', () => {
    editingPreset = null;
    renderModal();
  });

  card.querySelectorAll('[data-act-preset]').forEach(el => {
    el.addEventListener('click', async () => {
      try {
        await llmPresetsApi.activate(el.dataset.actPreset);
        await loadSettings();
        toast('已激活：' + el.dataset.actPreset, 'success');
        renderModal();
      } catch (e) { toast(e.message, 'danger'); }
    });
  });
  card.querySelectorAll('[data-edit-preset]').forEach(el => {
    el.addEventListener('click', () => {
      editingPreset = el.dataset.editPreset;
      renderModal();
    });
  });
  card.querySelectorAll('[data-del-preset]').forEach(el => {
    el.addEventListener('click', async () => {
      const name = el.dataset.delPreset;
      const snapshot = (settingsStore.state.llmPresets || []).find(p => p.name === name);
      if (!snapshot) return;
      try {
        await llmPresetsApi.delete(name);
        await loadSettings();
        renderModal();
        undoableToast(`已删除 preset「${name}」`, async () => {
          // 撤销：重新 upsert 这条 preset。注意 api_key 在 GET 时被掩码了，
          // 所以撤销恢复的 preset 需要用户重新填 key。
          await llmPresetsApi.upsert({
            name: snapshot.name,
            base_url: snapshot.base_url,
            model: snapshot.model,
            api_key: '',  // GET 接口不返回真实 key
            extra_headers: snapshot.extra_headers || '',
          });
          await loadSettings();
          renderModal();
          toast('已恢复（请重新填 API Key）', 'success');
        }, { kind: 'success' });
      } catch (e) { toast(e.message, 'danger'); }
    });
  });
}

// ─── ASR tab ─────────────────────────────────
function renderASRTab() {
  const a = settingsStore.state.asr || {};
  return `
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ 火山引擎实时 ASR</div>
    <div class="field"><label>WebSocket URL</label><input id="asr-url" type="text" value="${escapeHtml(a.wsUrl || 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async')}" placeholder="wss://..."></div>
    <div class="field"><label>App ID <span style="color:var(--char-soft);font-size:9px">(火山控制台数字 ID, 会作为 X-Api-App-Key)</span></label><input id="asr-appid" type="text" value="${escapeHtml(a.apiAppId || '')}"></div>
    <div class="field"><label>Access Token ${a.apiAccessKey_masked ? `<span style="color:var(--char-soft)">已存：${a.apiAccessKey_masked}</span>` : ''}</label><input id="asr-key" type="password" placeholder="留空则保留原值"></div>
    <div class="field"><label>Resource ID</label><input id="asr-rid" type="text" value="${escapeHtml(a.apiResourceId || 'volc.bigasr.sauc.duration')}"></div>

    <div class="ll-result" id="asr-result"></div>

    <div class="actions">
      <button class="btn" id="asr-test">测试握手</button>
      <button class="btn primary" id="asr-save">保存</button>
    </div>
  `;
}

function bindASRTab(card) {
  const get = () => ({
    wsUrl: card.querySelector('#asr-url').value.trim(),
    apiAppId: card.querySelector('#asr-appid').value.trim(),
    apiAccessKey: card.querySelector('#asr-key').value.trim(),
    apiResourceId: card.querySelector('#asr-rid').value.trim(),
  });
  const result = card.querySelector('#asr-result');

  card.querySelector('#asr-save').addEventListener('click', async () => {
    try {
      await asrConfigApi.put(get());
      await loadSettings();
      toast('已保存', 'success');
      renderModal();
    } catch (e) { toast(e.message, 'danger'); }
  });

  card.querySelector('#asr-test').addEventListener('click', async () => {
    result.textContent = '⋯ 握手中';
    try {
      // 先保存当前编辑值（不影响后端）
      const cfg = get();
      const r = await asrConfigApi.test(cfg);
      result.innerHTML = r.ok
        ? `<span style="color:var(--sage)">✓ ${escapeHtml(r.first_response || 'ok')}</span>`
        : `<span style="color:var(--rust)">✕ ${escapeHtml(r.error || 'failed')} <span style="color:var(--char-soft)">(${escapeHtml(r.stage || '')})</span></span>`;
    } catch (e) {
      result.innerHTML = `<span style="color:var(--rust)">✕ ${escapeHtml(e.message)}</span>`;
    }
  });
}

// ─── Profile tab ─────────────────────────────────
function renderProfileTab() {
  const p = settingsStore.state.profile || {};
  return `
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ 个人画像 — 自动注入 LLM system prompt</div>
    <div class="field"><label>角色</label><input id="pf-role" type="text" value="${escapeHtml(p.role || '')}" placeholder="后端 / K8s / GPU 云"></div>
    <div class="field"><label>求职目标</label><input id="pf-target" type="text" value="${escapeHtml(p.target || '')}" placeholder="平台开发工程师"></div>
    <div class="field"><label>经验</label><input id="pf-exp" type="text" value="${escapeHtml(p.experience || '')}" placeholder="<1 年 / 应届"></div>
    <div class="field">
      <label style="display:flex;align-items:center;gap:10px">
        System Prompt (写给 LLM 的"我是谁")
        <button class="btn ghost" id="pf-sync" style="font-size:9px;padding:3px 8px;margin-left:auto">↻ 从练习数据同步</button>
      </label>
      <textarea id="pf-sys" rows="8" placeholder="你是在帮一个 ... 的工程师准备面试 ...">${escapeHtml(p.system_prompt || '')}</textarea>
    </div>
    <div id="pf-sync-result" class="mono" style="font-size:10px;color:var(--char-soft);min-height:14px"></div>

    <div style="margin-top: 22px; padding-top: 16px; border-top: 1px dashed var(--line-paper-2)">
      <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ 数据备份</div>
      <div style="display:flex;align-items:center;gap:12px">
        <button class="btn" id="pf-export" style="font-size:10px;padding:6px 14px">⤓ 下载完整备份 (JSON)</button>
        <span class="mono" style="font-size:9px;color:var(--char-soft);letter-spacing:0.04em">包含 job_states / interviews / questions / resumes / settings — 不含 snapshot</span>
      </div>
    </div>

    <div class="actions">
      <button class="btn primary" id="pf-save">保存</button>
    </div>
  `;
}

function bindProfileTab(card) {
  card.querySelector('#pf-save').addEventListener('click', async () => {
    try {
      await settingsApi.putProfile({
        role: card.querySelector('#pf-role').value,
        target: card.querySelector('#pf-target').value,
        experience: card.querySelector('#pf-exp').value,
        system_prompt: card.querySelector('#pf-sys').value,
      });
      await loadSettings();
      toast('已保存', 'success');
    } catch (e) { toast(e.message, 'danger'); }
  });

  card.querySelector('#pf-export')?.addEventListener('click', () => {
    // 浏览器原生下载
    const a = document.createElement('a');
    a.href = '/api/v1/export';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast('已开始下载备份', 'success');
  });

  card.querySelector('#pf-sync').addEventListener('click', async () => {
    const btn = card.querySelector('#pf-sync');
    const result = card.querySelector('#pf-sync-result');
    btn.disabled = true;
    btn.textContent = '⋯ 同步中';
    result.textContent = '正在用 LLM 聚合你的练习数据并生成 system prompt …';
    try {
      const r = await profileApi.syncPrompt();
      card.querySelector('#pf-sys').value = r.system_prompt || '';
      result.innerHTML = `<span style="color:var(--sage)">✓ 已生成 — 别忘了点保存</span>`;
    } catch (e) {
      result.innerHTML = `<span style="color:var(--rust)">✕ ${escapeHtml(e.message)}</span>`;
    } finally {
      btn.disabled = false;
      btn.textContent = '↻ 从练习数据同步';
    }
  });
}

// ─── Prompts tab ─────────────────────────────────
function renderPromptsTab() {
  const items = settingsStore.state.prompts || [];
  const editing = editingPromptId
    ? items.find(p => p.id === editingPromptId)
    : null;

  const list = items.length === 0
    ? '<div class="empty-line">暂无模板</div>'
    : items.map(p => `
        <div class="preset-row ${p.id === editingPromptId ? 'active' : ''}">
          <span class="dot">▸</span>
          <span class="nm">${escapeHtml(p.name)}</span>
          <button data-edit-prompt="${escapeHtml(p.id)}">编辑</button>
          <button class="del" data-del-prompt="${escapeHtml(p.id)}">删</button>
        </div>
      `).join('');

  return `
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ Prompt 模板</div>
    <div class="preset-list">${list}</div>

    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin: 22px 0 10px">
      ◇ ${editing ? '编辑模板「' + escapeHtml(editing.name) + '」' : '新增模板'}
    </div>
    <div class="field"><label>名称</label><input id="pt-name" type="text" value="${escapeHtml(editing?.name || '')}" placeholder="STAR 答题"></div>
    <div class="field"><label>内容</label><textarea id="pt-content" rows="5" placeholder="请用 STAR 框架（Situation/Task/Action/Result）回答以下问题 ...">${escapeHtml(editing?.content || '')}</textarea></div>
    <div class="actions">
      ${editing ? '<button class="btn" id="pt-cancel">取消编辑</button>' : ''}
      <button class="btn primary" id="pt-save">${editing ? '保存修改' : '添加'}</button>
    </div>
  `;
}

function bindPromptsTab(card) {
  card.querySelector('#pt-save').addEventListener('click', async () => {
    const name = card.querySelector('#pt-name').value.trim();
    const content = card.querySelector('#pt-content').value.trim();
    if (!name || !content) return;
    try {
      const id = editingPromptId || ('pt_' + Date.now().toString(36));
      await promptTemplatesApi.upsert({ id, name, content });
      await loadSettings();
      toast(editingPromptId ? '已保存' : '已添加', 'success');
      editingPromptId = null;
      renderModal();
    } catch (e) { toast(e.message, 'danger'); }
  });

  card.querySelector('#pt-cancel')?.addEventListener('click', () => {
    editingPromptId = null;
    renderModal();
  });

  card.querySelectorAll('[data-edit-prompt]').forEach(el => {
    el.addEventListener('click', () => {
      editingPromptId = el.dataset.editPrompt;
      renderModal();
    });
  });

  card.querySelectorAll('[data-del-prompt]').forEach(el => {
    el.addEventListener('click', async () => {
      const id = el.dataset.delPrompt;
      const snapshot = (settingsStore.state.prompts || []).find(p => p.id === id);
      if (!snapshot) return;
      try {
        await promptTemplatesApi.delete(id);
        await loadSettings();
        renderModal();
        undoableToast(`已删除模板「${snapshot.name}」`, async () => {
          await promptTemplatesApi.upsert(snapshot);
          await loadSettings();
          renderModal();
          toast('已恢复', 'success');
        }, { kind: 'success' });
      } catch (e) { toast(e.message, 'danger'); }
    });
  });
}

// ─── 简历 tab ─────────────────────────────────
function renderResumesTab() {
  const items = settingsStore.state.resumes || [];
  const editing = editingResumeId
    ? (editingResumeId === 'new'
        ? editingResumeDraft
        : (items.find(r => r.id === editingResumeId) || null))
    : null;

  const list = items.length === 0
    ? '<div class="empty-line">还没有简历 — 点下方「新建」</div>'
    : items.map(r => {
        const prof = resumeProfiles[r.id];
        const isExtracting = extractingResumeId === r.id;
        const profCard = prof ? `
          <div class="resume-profile-card">
            <div><strong>${escapeHtml(prof.role || '—')}</strong> · ${escapeHtml(prof.seniority || '—')} · ${escapeHtml(prof.domain || '—')}</div>
            <div style="margin-top:4px">${(prof.skills || []).map(s => `<span class="chip">${escapeHtml(s)}</span>`).join(' ')}</div>
            ${(prof.projects || []).length ? `<div style="margin-top:6px;font-size:10px;color:var(--char-soft)">${(prof.projects || []).map(p => '· ' + escapeHtml(p.name || '') + (p.summary ? '：' + escapeHtml(p.summary) : '')).join('<br>')}</div>` : ''}
          </div>
        ` : '';
        return `
        <div class="preset-row ${r.id === editingResumeId ? 'active' : ''}">
          <span class="dot">${r.is_default ? '★' : '·'}</span>
          <span class="nm">${escapeHtml(r.name)}
            <span style="color:var(--char-soft);font-weight:400;font-size:9px;margin-left:6px">${(r.content || '').length} 字 · ${new Date(r.updated_at).toLocaleDateString('zh-CN')}</span>
          </span>
          ${r.is_default
            ? '<span style="font-family:var(--font-mono);font-size:9px;color:var(--amber-soft)">默认</span>'
            : `<button data-resume-default="${r.id}">设默认</button>`}
          <span style="display:flex;gap:4px">
            <button data-resume-extract="${r.id}" ${isExtracting ? 'disabled' : ''}>${isExtracting ? '抽取中…' : '✦ 画像'}</button>
            <button data-resume-edit="${r.id}">改</button>
            <button class="del" data-resume-del="${r.id}">删</button>
          </span>
        </div>
        ${profCard}
        `;
      }).join('');

  return `
    <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">◇ 简历版本</div>
    <div class="preset-list">${list}</div>

    ${editing ? `
      <div style="font-family:var(--font-mono);font-size:10px;color:var(--char-soft);text-transform:uppercase;letter-spacing:0.1em;margin: 22px 0 10px">
        ◇ ${editingResumeId === 'new' ? '新建简历' : '编辑「' + escapeHtml(editing.name) + '」'}
      </div>
      <div class="field"><label>名称</label><input id="rs-name" type="text" value="${escapeHtml(editing.name || '')}" placeholder="主投版 / GPU 云特化版 / 一页快投版"></div>
      <div class="field">
        <label>内容（Markdown 或纯文本均可）</label>
        <textarea id="rs-content" rows="14" style="font-family:var(--font-mono);font-size:12px;line-height:1.55">${escapeHtml(editing.content || '')}</textarea>
      </div>
      <div class="field" style="display:flex;align-items:center;gap:8px">
        <input id="rs-default" type="checkbox" ${editing.is_default ? 'checked' : ''} style="width:auto">
        <label for="rs-default" style="margin:0;cursor:pointer">设为默认简历</label>
      </div>
      <div class="actions">
        <button class="btn" id="rs-cancel">取消</button>
        <button class="btn primary" id="rs-save">${editingResumeId === 'new' ? '创建' : '保存'}</button>
      </div>
    ` : `
      <div class="actions">
        <button class="btn primary" id="rs-new">+ 新建简历</button>
      </div>
    `}
  `;
}

function bindResumesTab(card) {
  card.querySelector('#rs-new')?.addEventListener('click', () => {
    editingResumeId = 'new';
    editingResumeDraft = { name: '', content: '', is_default: false };
    renderModal();
  });

  card.querySelector('#rs-cancel')?.addEventListener('click', () => {
    editingResumeId = null;
    editingResumeDraft = { name: '', content: '', is_default: false };
    renderModal();
  });

  card.querySelector('#rs-save')?.addEventListener('click', async () => {
    const name = card.querySelector('#rs-name').value.trim();
    const content = card.querySelector('#rs-content').value;
    const is_default = card.querySelector('#rs-default').checked;
    if (!name) {
      toast('名称不能为空', 'danger');
      return;
    }
    try {
      if (editingResumeId === 'new') {
        await resumesApi.create({ name, content, is_default });
        toast('已创建', 'success');
      } else {
        await resumesApi.patch(editingResumeId, { name, content, is_default });
        toast('已保存', 'success');
      }
      await loadSettings();
      editingResumeId = null;
      renderModal();
    } catch (e) { toast(e.message, 'danger'); }
  });

  card.querySelectorAll('[data-resume-edit]').forEach(el => {
    el.addEventListener('click', () => {
      editingResumeId = el.dataset.resumeEdit;
      renderModal();
    });
  });

  // 懒加载每份简历的最新画像
  (settingsStore.state.resumes || []).forEach(r => {
    if (resumeProfiles[r.id] !== undefined) return;
    resumeProfiles[r.id] = null;
    resumeProfilesApi.listForResume(r.id).then(res => {
      resumeProfiles[r.id] = (res.items || [])[0] || null;
      renderModal();
    }).catch(() => {});
  });

  card.querySelectorAll('[data-resume-extract]').forEach(el => {
    el.addEventListener('click', async () => {
      const rid = el.dataset.resumeExtract;
      extractingResumeId = rid;
      renderModal();
      try {
        const profile = await resumeProfilesApi.extract(rid);
        resumeProfiles[rid] = profile;
        toast(`画像已生成：${profile.role || '?'}`, 'success');
      } catch (e) {
        toast('抽取失败：' + e.message, 'danger');
      } finally {
        extractingResumeId = null;
        renderModal();
      }
    });
  });

  card.querySelectorAll('[data-resume-default]').forEach(el => {
    el.addEventListener('click', async () => {
      try {
        await resumesApi.patch(el.dataset.resumeDefault, { is_default: true });
        await loadSettings();
        toast('已设为默认', 'success');
        renderModal();
      } catch (e) { toast(e.message, 'danger'); }
    });
  });

  card.querySelectorAll('[data-resume-del]').forEach(el => {
    el.addEventListener('click', async () => {
      const id = el.dataset.resumeDel;
      const snapshot = (settingsStore.state.resumes || []).find(r => r.id === id);
      if (!snapshot) return;
      try {
        await resumesApi.delete(id);
        await loadSettings();
        if (editingResumeId === id) editingResumeId = null;
        renderModal();
        undoableToast(`已删除简历「${snapshot.name}」`, async () => {
          await resumesApi.create({
            name: snapshot.name,
            content: snapshot.content,
            is_default: !!snapshot.is_default,
          });
          await loadSettings();
          renderModal();
          toast('已恢复', 'success');
        }, { kind: 'success' });
      } catch (e) { toast(e.message, 'danger'); }
    });
  });
}
