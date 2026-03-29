registerPage('users', async (container) => {
  let skip = 0;
  const limit = 50;

  async function load(s) {
    skip = s || 0;
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi(`/backoffice/collections/users/documents?skip=${skip}&limit=${limit}`);
      let html = '';

      html += '<div class="liquid-card"><h3>Users</h3>';
      html += renderTable(
        [
          { label: 'ID', key: '_id', render: r => `<code style="font-size:11px">${esc(r._id)}</code>` },
          { label: 'Email', key: 'email', render: r => `<strong>${esc(r.email)}</strong>` },
          { label: 'Display Name', key: 'display_name' },
          { label: 'Active', key: 'is_active', render: r => r.is_active ? '<span class="badge badge-ok">Yes</span>' : '<span class="badge badge-err">No</span>' },
          { label: 'Created', key: 'created_at', render: r => fmtDate(r.created_at) },
        ],
        d.items,
        r => `
          <button class="btn-ghost btn-sm" onclick="viewUserJson('${r._id}')">View</button>
          <button class="btn-destructive btn-sm" onclick="deleteUser('${r._id}')">Delete</button>
        `
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateUsers');
      html += '</div>';

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  window._paginateUsers = load;
  load(0);

  window.viewUserJson = async (id) => {
    try {
      const doc = await boApi(`/backoffice/collections/users/documents/${id}`);
      openModal('User Detail', `<div class="json-view">${esc(JSON.stringify(doc, null, 2))}</div>`);
    } catch (e) { alert(e.message); }
  };

  window.deleteUser = async (id) => {
    if (!confirm('Delete this user? This is irreversible.')) return;
    try {
      await boApi(`/backoffice/collections/users/documents/${id}`, { method: 'DELETE' });
      load(skip);
    } catch (e) { alert(e.message); }
  };
});
