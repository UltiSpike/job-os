// Text sanitizers — strip BOSS 直聘 PUA 字体混淆 & 整理空白
const PUA_RE = /[\uE000-\uF8FF]/g;

export function clean(s) {
  if (s == null) return '';
  return String(s)
    .replace(PUA_RE, '')
    .replace(/\r/g, '')
    .replace(/[ \t]+/g, ' ')
    .trim();
}

// 标题里常常被泄漏的薪资行污染（"AI平台\n-K·薪"），只保留第一行
export function cleanTitle(s) {
  if (!s) return '';
  const first = String(s).split('\n').map(x => clean(x)).filter(Boolean)[0] || '';
  // 去掉尾巴上残留的薪资碎片（有时候是 "xxxxxx K·薪" / "xxxxx 万·薪"）
  return first.replace(/\s*[\-·,，]?\s*[KkWw万]\s*·?\s*薪\s*$/u, '').trim();
}

export function cleanJD(s) {
  if (!s) return '';
  return String(s)
    .replace(PUA_RE, '')
    .replace(/\r/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

// 薪资字段直接清 PUA 即可（如果整段都是 PUA 就返回 "薪资保密"）
export function cleanSalary(s) {
  const c = clean(s);
  if (!c) return '';
  // 如果数字全无，意味着字体没解出来
  if (!/\d/.test(c)) return '面议';
  return c;
}
