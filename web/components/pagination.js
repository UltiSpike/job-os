// CLI-Editorial 分页器
//
// 设计：
// - 大号衬线斜体当前页 + 小号 mono 总页数
// - CLI prompt 前缀 ($ page ›)
// - scrubber 进度条 — 可点跳页
// - 左右大箭头按钮
// - 右下小字显示行数范围
//
// 使用：
//   renderPager({ pageIdx, total, count, range, jumpAttr, prevAttr, nextAttr })
//
// 在 mount 时调 bindPagerScrubber(rootEl, jumpHandler) 处理 scrubber 点击

export function renderPager({ pageIdx, total, count, range, prefix = 'data-pg', label = 'page' }) {
  const cur = pageIdx + 1;
  const pct = total > 1 ? (pageIdx / (total - 1)) * 100 : 0;
  const [start, end] = range || [0, count];

  return `
    <div class="epager">
      <button class="epager-arrow" ${prefix}="prev" ${pageIdx === 0 ? 'disabled' : ''} aria-label="上一页">◂</button>

      <div class="epager-center">
        <div class="epager-num">
          <span class="epager-prompt mono">$ ${label} ›</span>
          <span class="epager-cur">${cur}</span>
          <span class="epager-sep mono">/</span>
          <span class="epager-total mono">${total}</span>
        </div>
        <div class="epager-scrub" ${prefix}-scrub>
          <div class="epager-scrub-track"></div>
          <div class="epager-scrub-fill" style="width:${pct}%"></div>
          <div class="epager-scrub-marker" style="left:${pct}%"></div>
        </div>
      </div>

      <button class="epager-arrow" ${prefix}="next" ${pageIdx >= total - 1 ? 'disabled' : ''} aria-label="下一页">▸</button>

      <div class="epager-meta mono">${start + 1}–${end} <span class="of">of</span> ${count}</div>
    </div>
  `;
}

/**
 * 给 scrubber 绑定点击 → 跳页
 * @param {Element} rootEl
 * @param {string} prefix 跟 renderPager 用的一样
 * @param {(pageIdx: number) => void} onJump
 * @param {number} total
 */
export function bindPagerScrubber(rootEl, prefix, total, onJump) {
  const scrub = rootEl.querySelector(`[${prefix}-scrub]`);
  if (!scrub) return;
  scrub.addEventListener('click', (e) => {
    const rect = scrub.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, x / rect.width));
    const idx = Math.round(ratio * (total - 1));
    onJump(idx);
  });
}
