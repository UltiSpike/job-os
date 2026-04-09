// Job OS — entry. Router + bootstrap.
import { loadJobs, jobsStore } from './store/jobs.js';
import { loadQuestions, questionsStore } from './store/questions.js';
import { loadSettings, settingsStore } from './store/settings.js';
import { installCommandPalette } from './components/commandPalette.js';
import { todayView } from './views/today.js';
import { discoverView } from './views/discover.js';
import { pipelineView } from './views/pipeline.js';
import { trainingView } from './views/training.js';
import { curriculumView } from './views/curriculum.js';
import { decisionView } from './views/decision.js';
import { curriculumStore, loadCurriculum } from './store/curriculum.js';
import { openSettingsModal } from './views/_settingsModal.js';
import { fmtClock } from './components/dates.js';
import { toast } from './components/toast.js';

const VIEWS = [todayView, discoverView, pipelineView, trainingView, curriculumView, decisionView];

class Router {
  constructor() {
    this.current = 'today';
    this.root = document.getElementById('root');
  }

  go(name) {
    if (!VIEWS.find(v => v.name === name)) return;
    this.current = name;
    location.hash = '#/' + name;
    document.getElementById('cli-cmd').textContent = name;
    this.refresh();
  }

  refresh() {
    const view = VIEWS.find(v => v.name === this.current) || VIEWS[0];
    this.root.innerHTML = String(view.render());
    view.mount(this.root);
    this.renderTabs();
  }

  renderTabs() {
    const tabs = document.getElementById('tabs');
    tabs.innerHTML = VIEWS.map(v => {
      const badge = v.badge ? v.badge() : null;
      return `<button class="tab ${this.current === v.name ? 'active' : ''}" data-tab="${v.name}">
        ${v.label}
        ${badge ? `<span class="count">${badge}</span>` : ''}
      </button>`;
    }).join('');
    tabs.querySelectorAll('[data-tab]').forEach(el => {
      el.addEventListener('click', () => this.go(el.dataset.tab));
    });
  }
}

export const router = new Router();

async function boot() {
  const status = document.getElementById('cli-status');
  const setStatus = (s) => { if (status) status.textContent = s; };

  // initial hash route
  const hash = location.hash.replace('#/', '');
  if (hash && VIEWS.find(v => v.name === hash)) {
    router.current = hash;
  }
  document.getElementById('cli-cmd').textContent = router.current;

  // clock
  const clock = document.getElementById('clock');
  const tick = () => { if (clock) clock.textContent = fmtClock(); };
  tick(); setInterval(tick, 1000);

  // top bar settings
  document.querySelector('[data-action="open-settings"]')?.addEventListener('click', openSettingsModal);

  setStatus('loading…');
  try {
    await Promise.all([loadJobs(), loadQuestions(), loadSettings(), loadCurriculum()]);
  } catch (e) {
    toast('加载失败：' + e.message, 'danger');
  }

  // re-render whenever stores change
  const rerender = () => router.refresh();
  jobsStore.subscribe(rerender);
  questionsStore.subscribe(rerender);
  curriculumStore.subscribe(rerender);

  router.refresh();
  setStatus('ready');
  installCommandPalette();

  window.addEventListener('hashchange', () => {
    const h = location.hash.replace('#/', '');
    if (h && VIEWS.find(v => v.name === h) && h !== router.current) {
      router.current = h;
      document.getElementById('cli-cmd').textContent = h;
      router.refresh();
    }
  });
}

boot();
