// Tiny reactive store: Proxy + listener set.
// Works for objects of primitives + arrays. No deep magic.
export function createStore(initial) {
  const listeners = new Set();
  const target = { ...initial };

  const handler = {
    get(t, k) { return t[k]; },
    set(t, k, v) {
      if (t[k] === v) return true;
      t[k] = v;
      listeners.forEach((fn) => fn(t, k, v));
      return true;
    },
  };
  const state = new Proxy(target, handler);

  return {
    state,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    patch(p) { Object.assign(state, p); },
    snapshot() { return { ...target }; },
  };
}
