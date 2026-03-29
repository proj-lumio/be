registerPage('companies', async (container) => {
  let skip = 0;
  const limit = 50;

  async function load(s) {
    skip = s || 0;
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi(`/backoffice/collections/companies/documents?skip=${skip}&limit=${limit}`);
      let html = '';

      html += '<div class="liquid-card"><h3>Companies</h3>';
      html += renderTable(
        [
          { label: 'ID', key: '_id', render: r => `<code style="font-size:11px">${esc(r._id)}</code>` },
          { label: 'Name', key: 'name', render: r => `<strong>${esc(r.ragione_sociale || r.name)}</strong>` },
          { label: 'P.IVA', key: 'piva' },
          { label: 'Industry', key: 'industry' },
          { label: 'City', key: 'citta' },
          { label: 'Enriched', key: 'enriched_at', render: r => r.enriched_at ? '<span class="badge badge-ok">Yes</span>' : '<span class="badge badge-pending">No</span>' },
          { label: 'Created', key: 'created_at', render: r => fmtDate(r.created_at) },
        ],
        d.items,
        r => `
          <button class="btn-ghost btn-sm" onclick="viewCompanyDetail('${r._id}')">View</button>
          <button class="btn-ghost btn-sm" onclick="editCompany('${r._id}')">Edit</button>
          <button class="btn-destructive btn-sm" onclick="deleteCompany('${r._id}')">Delete</button>
        `
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateCompanies');
      html += '</div>';

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  window._paginateCompanies = load;
  load(0);

  window.viewCompanyDetail = async (id) => {
    try {
      const doc = await boApi(`/backoffice/collections/companies/documents/${id}`);
      openModal('Company Detail', `<div class="json-view">${esc(JSON.stringify(doc, null, 2))}</div>`);
    } catch (e) { alert(e.message); }
  };

  window.editCompany = async (id) => {
    try {
      const doc = await boApi(`/backoffice/collections/companies/documents/${id}`);
      const fields = ['name', 'piva', 'industry', 'description', 'website', 'citta', 'provincia', 'regione'];
      let body = '';
      for (const f of fields) {
        body += `<div class="form-group"><label>${f}</label><div class="liquid-input"><input id="edit-${f}" value="${esc(doc[f] || '')}"></div></div>`;
      }
      openModal(
        `Edit: ${doc.name || doc._id}`,
        body,
        `<button class="btn-outline" onclick="closeModal()">Cancel</button>
         <button class="btn-action" onclick="saveCompany('${id}')">Save</button>`
      );
    } catch (e) { alert(e.message); }
  };

  window.saveCompany = async (id) => {
    const fields = ['name', 'piva', 'industry', 'description', 'website', 'citta', 'provincia', 'regione'];
    const body = {};
    for (const f of fields) {
      const v = document.getElementById(`edit-${f}`)?.value;
      if (v !== undefined && v !== '') body[f] = v;
    }
    try {
      await boApi(`/backoffice/collections/companies/documents/${id}`, { method: 'PUT', body });
      closeModal();
      load(skip);
    } catch (e) { alert(e.message); }
  };

  window.deleteCompany = async (id) => {
    if (!confirm('Delete this company? This is irreversible.')) return;
    try {
      await boApi(`/backoffice/collections/companies/documents/${id}`, { method: 'DELETE' });
      load(skip);
    } catch (e) { alert(e.message); }
  };
});
