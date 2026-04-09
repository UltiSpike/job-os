// Reward toast — 行为强化用，显示 mastery / 进度变化
//
// 用法：
//   import { rewardToast, masteryDeltaToast } from '../components/rewardToast.js';
//   rewardToast({ icon: '✓', title: 'Service ClusterIP 通过', subtitle: '掌握度 60% → 75% (+15)' });
//   masteryDeltaToast(beforeMastery, afterMastery, conceptName);

const STACK_ID = 'toast-stack';

export function rewardToast({ icon = '✓', title = '', subtitle = '', kind = 'success', timeout = 3500, onClick = null }) {
  const stack = document.getElementById(STACK_ID);
  if (!stack) return;
  const el = document.createElement('div');
  el.className = `toast reward ${kind}`;
  el.innerHTML = `
    <span class="reward-icon"></span>
    <span class="reward-body">
      <span class="reward-title"></span>
      <span class="reward-subtitle"></span>
    </span>
  `;
  el.querySelector('.reward-icon').textContent = icon;
  el.querySelector('.reward-title').textContent = title;
  el.querySelector('.reward-subtitle').textContent = subtitle;
  if (onClick) {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => { onClick(); });
  }
  stack.appendChild(el);
  // animate in
  requestAnimationFrame(() => {
    el.classList.add('show');
  });
  setTimeout(() => {
    el.classList.remove('show');
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    el.style.transition = 'all 0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, timeout);
}

/**
 * Convenience: 计算 mastery 变化并自动决定语调
 */
export function masteryDeltaToast(before, after, conceptName) {
  if (!after) return;
  const beforePct = before ? Math.round((before.score || 0) * 100) : 0;
  const afterPct  = Math.round((after.score || 0) * 100);
  const delta = afterPct - beforePct;
  if (delta === 0 && !before) {
    rewardToast({
      icon: '✓',
      title: `${conceptName} 进度已记录`,
      subtitle: `当前掌握度 ${afterPct}%`,
    });
    return;
  }
  if (delta > 0) {
    rewardToast({
      icon: '↑',
      title: `${conceptName} +${delta}`,
      subtitle: `掌握度 ${beforePct}% → ${afterPct}%`,
      kind: 'success',
    });
  } else if (delta < 0) {
    rewardToast({
      icon: '↓',
      title: `${conceptName} ${delta}`,
      subtitle: `掌握度 ${beforePct}% → ${afterPct}%`,
      kind: 'warn',
    });
  } else {
    rewardToast({
      icon: '✓',
      title: `${conceptName} 已巩固`,
      subtitle: `掌握度 ${afterPct}%`,
    });
  }
}
