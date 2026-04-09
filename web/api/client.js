// Minimal fetch wrapper. BFF is same-origin (FastAPI mounts /web).
const BASE = '/api/v1';

async function request(method, path, { body, query } = {}) {
  let url = BASE + path;
  if (query) {
    const qs = new URLSearchParams(
      Object.entries(query).filter(([, v]) => v != null && v !== '')
    ).toString();
    if (qs) url += '?' + qs;
  }
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 160)}`);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

export const api = {
  get:    (p, query)       => request('GET',    p, { query }),
  post:   (p, body, query) => request('POST',   p, { body, query }),
  put:    (p, body)        => request('PUT',    p, { body }),
  patch:  (p, body)        => request('PATCH',  p, { body }),
  delete: (p)              => request('DELETE', p),
};
