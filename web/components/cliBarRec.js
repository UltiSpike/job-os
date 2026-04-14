// 把 today recommendation 挂到 cli-bar 右半边
//
// 设计原则：CLI 美学下不再加新 chrome — 复用已有的 cli-bar 这条 status line。
// 没数据 → hidden，cli-bar 看起来跟原来一致。
import { meStore } from '../store/me.js';

const REC_ID = 'cli-rec';

function render() {
  const el = document.getElementById(REC_ID);
  if (!el) return;
  const rec = meStore.state.todayRec;

  if (!rec || rec.kind === 'empty') {
    el.classList.add('hidden');
    el.textContent = '';
    el.removeAttribute('href');
    return;
  }
  el.classList.remove('hidden');
  el.href = rec.url || '#/me';
  el.title = rec.label || '';
  el.textContent = `▸ ${rec.label} ▶`;
}

export function installCliBarRec() {
  render();
  meStore.subscribe(render);
}
