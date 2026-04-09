// Persistent strip — 顶部一条"今日待办"快捷入口
//
// 在 app.js boot 后挂一次。订阅 meStore，自动 graceful degrade：
// 没数据 = 整条消失，不渲染空状态。
import { meStore } from '../store/me.js';

const STRIP_ID = 'persistent-strip';

function ensureContainer() {
  let el = document.getElementById(STRIP_ID);
  if (el) return el;
  el = document.createElement('div');
  el.id = STRIP_ID;
  el.className = 'persistent-strip hidden';
  // 插入到 #tabs 之前 (即 app top bar 下方)
  const tabs = document.getElementById('tabs');
  if (tabs && tabs.parentNode) {
    tabs.parentNode.insertBefore(el, tabs);
  } else {
    document.body.prepend(el);
  }
  return el;
}

function render() {
  const el = ensureContainer();
  const rec = meStore.state.todayRec;
  const cov = meStore.state.coverage;

  // graceful: 没有任何推荐、也没有 coverage 信号 → 隐藏
  if (!rec || rec.kind === 'empty') {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }

  const covPart = (cov && !cov.fallback && cov.total > 0)
    ? `<span class="strip-cov">覆盖度 ${Math.round((cov.percentage || 0) * 100)}%</span>`
    : '';

  el.classList.remove('hidden');
  el.innerHTML = `
    <span class="strip-label">${rec.label || '今日推荐'}</span>
    ${covPart}
    <a class="strip-go" href="${rec.url || '#/today'}">▶ 开始</a>
  `;
}

export function installPersistentStrip() {
  ensureContainer();
  render();
  meStore.subscribe(render);
}
