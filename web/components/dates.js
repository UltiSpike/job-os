// Date helpers
export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export function daysSince(iso) {
  if (!iso) return 0;
  const d = new Date(iso);
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

export function hoursUntil(iso) {
  if (!iso) return -1;
  const d = new Date(iso);
  return (d.getTime() - Date.now()) / 3600000;
}

export function fmtRelativeFuture(iso) {
  const h = hoursUntil(iso);
  if (h < 0) return '已过期';
  if (h < 1) return Math.round(h * 60) + 'm';
  if (h < 24) return Math.round(h) + 'h';
  return Math.round(h / 24) + 'd';
}

export function fmtClock() {
  const d = new Date();
  return d.toTimeString().slice(0, 8);
}
