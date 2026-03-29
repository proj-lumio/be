/* ── Lumio Backoffice — Core ── */

const API = () => document.getElementById('api-url').value;

// ── Auth ──
async function doLogin() {
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';

  if (!email || !password) { errEl.textContent = 'Email and password required'; return; }

  try {
    const res = await fetch(`${API()}/api/v1/backoffice/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const d = await res.json();
      throw new Error(d.detail || 'Invalid credentials');
    }
    sessionStorage.setItem('bo_auth', email);
    showApp();
  } catch (e) {
    errEl.textContent = e.message;
  }
}

function doLogout() {
  sessionStorage.removeItem('bo_auth');
  location.reload();
}

function showApp() {
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  document.getElementById('bo-user-badge').textContent = sessionStorage.getItem('bo_auth') || 'admin';
  checkHealth();
  navigateTo('dashboard');
  initNav();
}

// ── API helper ──
async function boApi(path, opts = {}) {
  const url = `${API()}/api/v1${path}`;
  const config = { headers: {}, ...opts };
  if (opts.body && !(opts.body instanceof FormData)) {
    config.headers['Content-Type'] = 'application/json';
    config.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, config);
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
  return data;
}

// ── Health ──
async function checkHealth() {
  const badge = document.getElementById('health-badge');
  try {
    const d = await boApi('/health');
    badge.textContent = `${d.service} v${d.version}`;
    badge.className = 'badge badge-ok';
  } catch {
    badge.textContent = 'offline';
    badge.className = 'badge badge-err';
  }
}

// ── Navigation ──
const pages = {};

function registerPage(name, renderFn) {
  pages[name] = renderFn;
}

function navigateTo(name) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === name));
  const title = document.getElementById('page-title');
  title.textContent = name.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const content = document.getElementById('page-content');
  content.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
  if (pages[name]) {
    pages[name](content);
  } else {
    content.innerHTML = '<div class="empty-state">Page not found</div>';
  }
}

function initNav() {
  document.getElementById('sidebar-nav').addEventListener('click', e => {
    const btn = e.target.closest('.nav-item');
    if (btn) navigateTo(btn.dataset.page);
  });
}

// ── Utilities ──
function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function fmtDate(d) {
  if (!d) return '-';
  try { return new Date(d).toLocaleString(); } catch { return d; }
}

function truncate(s, len = 60) {
  if (!s) return '-';
  s = String(s);
  return s.length > len ? s.slice(0, len) + '...' : s;
}

function fmtNum(n) { return (n || 0).toLocaleString(); }

// ── Modal ──
function openModal(title, bodyHtml, footerHtml) {
  closeModal();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'modal-overlay';
  overlay.onclick = e => { if (e.target === overlay) closeModal(); };
  overlay.innerHTML = `
    <div class="modal liquid-card-strong">
      <div class="modal-header">
        <h3>${title}</h3>
        <button class="btn-ghost" onclick="closeModal()">&times;</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}
    </div>`;
  document.body.appendChild(overlay);
}

function closeModal() {
  const m = document.getElementById('modal-overlay');
  if (m) m.remove();
}

// ── Pagination helper ──
// onPage is a global function name string, e.g. "window._paginate"
function renderPagination(total, skip, limit, onPageName) {
  const page = Math.floor(skip / limit) + 1;
  const totalPages = Math.ceil(total / limit);
  return `
    <div class="pagination">
      <span>${total} record(s) — page ${page}/${totalPages || 1}</span>
      <div class="pagination-buttons">
        <button class="btn-outline btn-sm" ${skip === 0 ? 'disabled' : ''} onclick="${onPageName}(${skip - limit})">Prev</button>
        <button class="btn-outline btn-sm" ${skip + limit >= total ? 'disabled' : ''} onclick="${onPageName}(${skip + limit})">Next</button>
      </div>
    </div>`;
}

// ── Table renderer ──
function renderTable(columns, rows, actions) {
  if (!rows.length) return '<div class="empty-state">No records</div>';
  let html = '<div style="overflow-x:auto"><table class="data-table"><thead><tr>';
  for (const col of columns) {
    html += `<th>${esc(col.label)}</th>`;
  }
  if (actions) html += '<th>Actions</th>';
  html += '</tr></thead><tbody>';
  for (const row of rows) {
    html += '<tr>';
    for (const col of columns) {
      const val = col.render ? col.render(row) : esc(truncate(row[col.key]));
      html += `<td>${val}</td>`;
    }
    if (actions) html += `<td class="actions">${actions(row)}</td>`;
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  return html;
}
