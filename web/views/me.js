// Me view — 这个 app 的主语 / 个人全景
//
// 4 种渲染模式（独立可用 / 渐进增强）：
//   empty       — 啥都没有 → 引导用户填简历或加目标
//   basic       — 有 user_profile 但没 mastery → 显示个人信息
//   half-active — 有 mastery 但没 target → mastery 全景
//   full        — 有 mastery + target → 完整仪表盘
import { html, raw } from '../components/html.js';
import { meStore, loadMe, patchMe, getCurriculumUrl } from '../store/me.js';
import { settingsStore } from '../store/settings.js';
import { jobsStore } from '../store/jobs.js';
import { toast } from '../components/toast.js';

let editingBio = false;
let bioDraft = '';

function renderMode(profile, mastery, target, coverage) {
  // 决定渲染模式
  const hasProfile = profile && (profile.bio || profile.target_role || profile.active_resume_id);
  const hasMastery = (mastery || []).some(m => (m.n_questions_touched || 0) > 0);
  const hasTarget = target && Object.keys(target).length > 0;

  if (!hasProfile && !hasMastery && !hasTarget) return 'empty';
  if (hasMastery && hasTarget) return 'full';
  if (hasMastery) return 'half-active';
  return 'basic';
}

function renderEmpty() {
  return html`
    <div class="me-empty">
      <h2>欢迎</h2>
      <p>先做一件事让 app 认识你：</p>
      <div class="me-empty-actions">
        <a class="btn primary" href="javascript:void(0)" data-action="add-resume">写一份简历</a>
        <a class="btn" href="#/discover">浏览岗位</a>
        <a class="btn" href="#/curriculum">先学一节课</a>
      </div>
      <p class="me-empty-hint">独立可用：你不必先做这些才能用 training/curriculum，但做了之后所有 tab 都会变得更聪明。</p>
    </div>
  `;
}

function renderProfileCard(profile) {
  const resumes = settingsStore.state.resumes || [];
  const activeResume = profile.active_resume_id
    ? resumes.find(r => r.id === profile.active_resume_id)
    : (resumes.find(r => r.is_default) || resumes[0]);
  return html`
    <section class="me-profile">
      <h3>◇ 你是谁</h3>
      <div class="me-bio">
        ${editingBio ? html`
          <textarea id="me-bio-ta" rows="3" placeholder="一句话介绍自己 / 当前位置 / 想去哪">${bioDraft}</textarea>
          <div class="me-bio-actions">
            <button class="btn" data-bio-cancel>取消</button>
            <button class="btn primary" data-bio-save>保存</button>
          </div>
        ` : html`
          <div class="me-bio-text" data-bio-edit>
            ${profile.bio || raw('<span class="me-bio-empty">点击写一句自述</span>')}
          </div>
        `}
      </div>
      <dl class="me-meta">
        <dt>当前角色</dt><dd>${profile.current_role || '—'}</dd>
        <dt>目标角色</dt><dd>${profile.target_role || '—'}</dd>
        <dt>当前简历</dt><dd>${activeResume ? activeResume.name : '未选择'}</dd>
      </dl>
    </section>
  `;
}

function renderTargetCard(profile) {
  const allJobs = jobsStore.state.jobs || [];
  const active = (profile.active_target_job_hrefs || []).slice(0, 8);
  const activeJobs = active.map(href => allJobs.find(j => j.href === href)).filter(Boolean);
  return html`
    <section class="me-target">
      <h3>◇ 目标岗位 (${active.length})</h3>
      ${activeJobs.length === 0 ? html`
        <div class="me-empty-line">
          没有 active target —
          <a href="#/pipeline">去 pipeline 设定</a>
        </div>
      ` : html`
        <ul class="me-target-list">
          ${activeJobs.map(j => html`
            <li>
              <span class="me-tj-title">${j.title}</span>
              <span class="me-tj-co">${j.company || ''}</span>
              <span class="me-tj-tier">${j.tier || ''}</span>
            </li>
          `)}
        </ul>
      `}
    </section>
  `;
}

function renderMasteryCard(mastery, coverage) {
  const total = mastery.length;
  const touched = mastery.filter(m => (m.n_questions_touched || 0) > 0).length;
  const mastered = mastery.filter(m => m.status === 'mastered').length;
  const learning = mastery.filter(m => m.status === 'learning').length;
  const rusty = mastery.filter(m => m.status === 'rusty').length;
  const untouched = mastery.filter(m => m.status === 'untouched').length;

  return html`
    <section class="me-mastery">
      <h3>◇ 当前掌握 ${coverage && !coverage.fallback ? raw(`<span class="me-cov">目标覆盖度 ${Math.round((coverage.percentage || 0) * 100)}% (${coverage.covered}/${coverage.total})</span>`) : ''}</h3>
      <div class="me-mastery-stats">
        <span class="me-stat ms-mastered">${mastered} 已掌握</span>
        <span class="me-stat ms-learning">${learning} 学习中</span>
        <span class="me-stat ms-rusty">${rusty} 需复习</span>
        <span class="me-stat ms-untouched">${untouched} 未学</span>
        <span class="me-stat-total">/ ${total}</span>
      </div>
      <h4>最弱 5 个</h4>
      <ul class="me-weakest">
        ${mastery.slice(0, 5).map(m => {
          const pct = Math.round((m.score || 0) * 100);
          return html`
            <li>
              <a href="${getCurriculumUrl(m.concept_slug)}">
                <span class="mw-name">${m.concept_name || m.concept_slug}</span>
                <span class="mw-score">${pct}%</span>
                <span class="mw-status mw-${m.status}">${m.status}</span>
              </a>
            </li>
          `;
        })}
      </ul>
    </section>
  `;
}

function renderTodayCard(rec) {
  if (!rec || rec.kind === 'empty') return '';
  return html`
    <section class="me-today">
      <h3>◇ 今日推荐</h3>
      <a class="me-today-card" href="${rec.url || '#/today'}">
        <span class="me-today-kind">${rec.kind}</span>
        <span class="me-today-label">${rec.label}</span>
        <span class="me-today-arrow">▶</span>
      </a>
    </section>
  `;
}

export const meView = {
  name: 'me',
  label: 'me',
  badge: () => {
    const cov = meStore.state.coverage;
    if (!cov || cov.fallback || cov.total === 0) return null;
    return Math.round((cov.percentage || 0) * 100) + '%';
  },
  render() {
    const { profile, mastery, target, coverage, todayRec, loaded } = meStore.state;
    if (!loaded) {
      return html`
        <section class="view view-me">
          <header class="page-head">
            <div class="page-num">000 / ME</div>
            <h1 class="page-title">我<span class="accent">.</span></h1>
            <p class="page-lede">载入中…</p>
          </header>
        </section>
      `;
    }

    const mode = renderMode(profile, mastery, target, coverage);

    return html`
      <section class="view view-me">
        <header class="page-head">
          <div class="page-num">000 / ME</div>
          <h1 class="page-title">我<span class="accent">.</span></h1>
          <p class="page-lede">这个 app 的主语 — 你声称会的、想去的、实际掌握的，全在这里。</p>
        </header>

        ${mode === 'empty' ? renderEmpty() : html`
          <div class="me-grid">
            ${renderProfileCard(profile || {})}
            ${renderTodayCard(todayRec)}
            ${(mode === 'full' || mode === 'half-active') ? renderMasteryCard(mastery, coverage) : ''}
            ${renderTargetCard(profile || {})}
          </div>
        `}
      </section>
    `;
  },
  mount(root) {
    if (!meStore.state.loaded) {
      loadMe();
    }
    root.querySelector('[data-bio-edit]')?.addEventListener('click', () => {
      bioDraft = meStore.state.profile?.bio || '';
      editingBio = true;
      import('../app.js').then(({ router }) => router.refresh());
    });
    root.querySelector('[data-bio-cancel]')?.addEventListener('click', () => {
      editingBio = false;
      import('../app.js').then(({ router }) => router.refresh());
    });
    root.querySelector('[data-bio-save]')?.addEventListener('click', async () => {
      const ta = root.querySelector('#me-bio-ta');
      const v = ta?.value || '';
      try {
        await patchMe({ bio: v });
        editingBio = false;
        toast('已保存', 'success');
        import('../app.js').then(({ router }) => router.refresh());
      } catch (e) {
        toast('保存失败：' + e.message, 'danger');
      }
    });
    root.querySelector('#me-bio-ta')?.addEventListener('input', (e) => {
      bioDraft = e.target.value;
    });
    root.querySelector('[data-action="add-resume"]')?.addEventListener('click', () => {
      // 触发 settings modal 直接到简历 tab — 复用现有入口
      import('./_settingsModal.js').then(m => m.openSettingsModal && m.openSettingsModal('resumes'));
    });
  },
};
