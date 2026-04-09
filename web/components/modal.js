// Minimal modal: render arbitrary HTML + bind handlers.
const HOST_ID = 'modal-host';

let currentClose = null;

export function openModal({ title, sub = '', body, actions = '', onMount, wide = false }) {
  closeModal();
  const host = document.getElementById(HOST_ID);
  host.innerHTML = `
    <div class="modal-overlay" data-close></div>
    <div class="modal-card ${wide ? 'wide' : ''}">
      <button class="close" data-close>✕</button>
      <h2>${title}</h2>
      ${sub ? `<div class="sub">${sub}</div>` : ''}
      <div class="modal-body">${body}</div>
      ${actions ? `<div class="actions">${actions}</div>` : ''}
    </div>
  `;
  host.classList.add('open');

  const onClick = (e) => {
    if (e.target.matches('[data-close]')) closeModal();
  };
  const onKey = (e) => {
    if (e.key === 'Escape') closeModal();
  };
  host.addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);

  currentClose = () => {
    host.removeEventListener('click', onClick);
    document.removeEventListener('keydown', onKey);
    host.classList.remove('open');
    host.innerHTML = '';
    currentClose = null;
  };

  if (onMount) onMount(host.querySelector('.modal-card'));
}

export function closeModal() {
  if (currentClose) currentClose();
}
