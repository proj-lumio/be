registerPage('documents', async (container) => {
  let skip = 0;
  const limit = 50;

  async function load(s) {
    skip = s || 0;
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi(`/backoffice/collections/documents/documents?skip=${skip}&limit=${limit}`);
      let html = '';

      html += '<div class="liquid-card"><h3>Documents</h3>';
      const icons = { pdf: '📄', docx: '📝', xlsx: '📊', pptx: '📑', txt: '📃', audio: '🎵', video: '🎬', image: '🖼️' };
      html += renderTable(
        [
          { label: 'ID', key: '_id', render: r => `<code style="font-size:11px">${esc(r._id)}</code>` },
          { label: 'Filename', key: 'filename', render: r => `${icons[r.doc_type] || '📎'} <strong>${esc(r.filename)}</strong>` },
          { label: 'Type', key: 'doc_type' },
          { label: 'Size', key: 'file_size', render: r => r.file_size ? `${(r.file_size / 1024).toFixed(1)} KB` : '-' },
          { label: 'Chunks', key: 'chunks_count', render: r => fmtNum(r.chunks_count) },
          { label: 'Status', key: 'processing_status', render: r => {
            const cls = r.processing_status === 'completed' ? 'badge-ok' : r.processing_status === 'failed' ? 'badge-err' : 'badge-pending';
            return `<span class="badge ${cls}">${esc(r.processing_status)}</span>`;
          }},
          { label: 'Company ID', key: 'company_id', render: r => `<code style="font-size:11px">${esc(truncate(r.company_id, 12))}</code>` },
          { label: 'Created', key: 'created_at', render: r => fmtDate(r.created_at) },
        ],
        d.items,
        r => `
          <button class="btn-ghost btn-sm" onclick="viewDocJson('${r._id}')">View</button>
          <button class="btn-destructive btn-sm" onclick="deleteDoc('${r._id}')">Delete</button>
        `
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateDocs');
      html += '</div>';

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  window._paginateDocs = load;
  load(0);

  window.viewDocJson = async (id) => {
    try {
      const doc = await boApi(`/backoffice/collections/documents/documents/${id}`);
      openModal('Document Detail', `<div class="json-view">${esc(JSON.stringify(doc, null, 2))}</div>`);
    } catch (e) { alert(e.message); }
  };

  window.deleteDoc = async (id) => {
    if (!confirm('Delete this document record?')) return;
    try {
      await boApi(`/backoffice/collections/documents/documents/${id}`, { method: 'DELETE' });
      load(skip);
    } catch (e) { alert(e.message); }
  };
});
