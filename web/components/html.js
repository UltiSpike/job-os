// Tagged template helpers — no framework, just safe string building.
export function escapeHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function escapeAttr(s) {
  return escapeHtml(s);
}

// Tag for "trust this fragment, do not escape"
export class Raw {
  constructor(html) { this.html = html; }
  toString() { return this.html; }
}
export const raw = (s) => new Raw(s);

// Tagged template literal: html`<p>${userInput}</p>` auto-escapes interpolations.
// Returns Raw so nested html`...` calls don't get escaped by their parent.
export function html(strings, ...values) {
  let out = '';
  for (let i = 0; i < strings.length; i++) {
    out += strings[i];
    if (i < values.length) {
      out += renderValue(values[i]);
    }
  }
  return new Raw(out);
}

function renderValue(v) {
  if (v == null || v === false) return '';
  if (v instanceof Raw) return v.html;
  if (Array.isArray(v)) return v.map(renderValue).join('');
  if (typeof v === 'number') return String(v);
  return escapeHtml(v);
}
