const STACK_ID = 'toast-stack';

export function toast(msg, kind = '') {
  const stack = document.getElementById(STACK_ID);
  if (!stack) return;
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    el.style.transition = 'all 0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, 2600);
}

/**
 * 可撤销 toast — 显示一个带按钮的 toast，timeout 内点击则触发 onAction
 *
 * @param {string} msg            主文案
 * @param {Function} onAction     点击按钮的回调（async 也行）
 * @param {Object} opts
 * @param {number} opts.timeout   显示毫秒数（默认 5000）
 * @param {string} opts.kind      'success' / 'danger'
 * @param {string} opts.actionLabel 按钮文案，默认 "撤销"
 */
export function undoableToast(msg, onAction, opts = {}) {
  const stack = document.getElementById(STACK_ID);
  if (!stack) return;
  const timeout = opts.timeout ?? 5000;
  const kind = opts.kind || '';
  const actionLabel = opts.actionLabel || '撤销';

  const el = document.createElement('div');
  el.className = `toast undoable ${kind}`;
  el.innerHTML = `
    <span class="toast-msg"></span>
    <button class="toast-undo" type="button"></button>
    <span class="toast-timer" aria-hidden="true"></span>
  `;
  el.querySelector('.toast-undo').textContent = actionLabel;
  el.querySelector('.toast-msg').textContent = msg;
  stack.appendChild(el);

  let undone = false;
  const startTs = Date.now();
  const timerEl = el.querySelector('.toast-timer');

  const tick = setInterval(() => {
    const left = Math.max(0, timeout - (Date.now() - startTs));
    const pct = Math.round((left / timeout) * 100);
    if (timerEl) timerEl.style.width = pct + '%';
  }, 50);

  const cleanup = () => {
    clearInterval(tick);
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    el.style.transition = 'all 0.3s ease';
    setTimeout(() => el.remove(), 300);
  };

  el.querySelector('.toast-undo').addEventListener('click', async () => {
    if (undone) return;
    undone = true;
    cleanup();
    try { await onAction(); }
    catch (e) { toast('操作失败：' + e.message, 'danger'); }
  });

  setTimeout(() => { if (!undone) cleanup(); }, timeout);
}
