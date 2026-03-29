registerPage('collections', async (container) => {
  let currentCollection = null;
  let skip = 0;
  const limit = 50;

  async function loadCollections() {
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi('/backoffice/collections');
      let html = '<div class="liquid-card"><h3>Raw Collections Browser</h3>';
      html += '<div class="toolbar">';
      html += '<select id="coll-select" onchange="window._browseCollection(this.value)" style="padding:8px 12px;background:rgba(255,255,255,0.06);border:1px solid var(--border);border-radius:12px;color:var(--foreground);font-size:13px;min-width:200px">';
      html += '<option value="">Select a collection...</option>';
      for (const c of d.collections) {
        const sel = c.name === currentCollection ? 'selected' : '';
        html += `<option value="${esc(c.name)}" ${sel}>${esc(c.name)} (${fmtNum(c.count)})</option>`;
      }
      html += '</select></div>';
      html += '<div id="coll-content"></div>';
      html += '</div>';
      container.innerHTML = html;

      if (currentCollection) {
        loadDocs(0);
      }
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  async function loadDocs(s) {
    skip = s || 0;
    if (!currentCollection) return;
    const content = document.getElementById('coll-content');
    if (!content) return;
    content.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';

    try {
      const d = await boApi(`/backoffice/collections/${currentCollection}/documents?skip=${skip}&limit=${limit}`);

      if (!d.items.length) {
        content.innerHTML = '<div class="empty-state">Collection is empty</div>';
        return;
      }

      // Auto-detect columns from first doc
      const allKeys = new Set();
      for (const item of d.items) {
        for (const k of Object.keys(item)) allKeys.add(k);
      }
      const keys = Array.from(allKeys).slice(0, 8);

      let html = renderTable(
        keys.map(k => ({
          label: k,
          key: k,
          render: r => {
            const v = r[k];
            if (v === null || v === undefined) return '<span style="color:var(--muted-foreground)">null</span>';
            if (typeof v === 'object') return `<code style="font-size:11px">${esc(truncate(JSON.stringify(v), 40))}</code>`;
            return esc(truncate(String(v), 40));
          }
        })),
        d.items,
        r => `
          <button class="btn-ghost btn-sm" onclick="viewRawDoc('${currentCollection}','${r._id}')">View</button>
          <button class="btn-ghost btn-sm" onclick="editRawDoc('${currentCollection}','${r._id}')">Edit</button>
          <button class="btn-destructive btn-sm" onclick="deleteRawDoc('${currentCollection}','${r._id}')">Delete</button>
        `
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateRaw');
      content.innerHTML = html;
    } catch (e) {
      content.innerHTML = `<p style="color:var(--destructive)">Error: ${esc(e.message)}</p>`;
    }
  }

  window._paginateRaw = loadDocs;

  window._browseCollection = (name) => {
    currentCollection = name;
    if (name) loadDocs(0);
  };

  loadCollections();

  window.viewRawDoc = async (coll, id) => {
    try {
      const doc = await boApi(`/backoffice/collections/${coll}/documents/${id}`);
      openModal(`${coll} / ${id}`, `<div class="json-view">${esc(JSON.stringify(doc, null, 2))}</div>`);
    } catch (e) { alert(e.message); }
  };

  window.editRawDoc = async (coll, id) => {
    try {
      const doc = await boApi(`/backoffice/collections/${coll}/documents/${id}`);
      const editable = { ...doc };
      delete editable._id;

      openModal(
        `Edit: ${coll} / ${id}`,
        `<div class="form-group">
          <label>JSON Document (edit below)</label>
          <div class="liquid-input" style="height:auto">
            <textarea id="raw-edit-json" style="min-height:300px;font-family:'Cascadia Code','Fira Code',monospace;font-size:12px;line-height:1.5;padding:14px 16px">${esc(JSON.stringify(editable, null, 2))}</textarea>
          </div>
        </div>`,
        `<button class="btn-outline" onclick="closeModal()">Cancel</button>
         <button class="btn-action" onclick="saveRawDoc('${coll}','${id}')">Save</button>`
      );
    } catch (e) { alert(e.message); }
  };

  window.saveRawDoc = async (coll, id) => {
    const raw = document.getElementById('raw-edit-json')?.value;
    if (!raw) return;
    try {
      const body = JSON.parse(raw);
      await boApi(`/backoffice/collections/${coll}/documents/${id}`, { method: 'PUT', body });
      closeModal();
      loadDocs(skip);
    } catch (e) { alert(e.message); }
  };

  window.deleteRawDoc = async (coll, id) => {
    if (!confirm('Delete this document? This is irreversible.')) return;
    try {
      await boApi(`/backoffice/collections/${coll}/documents/${id}`, { method: 'DELETE' });
      loadDocs(skip);
    } catch (e) { alert(e.message); }
  };
});
