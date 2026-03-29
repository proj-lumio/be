registerPage('dashboard', async (container) => {
  container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading dashboard...</div>';
  try {
    const collections = await boApi('/backoffice/collections');
    const colls = collections.collections;
    const totalDocs = colls.reduce((s, c) => s + c.count, 0);

    let html = '<div class="stats-grid">';
    html += `<div class="stat-card liquid-card-btn"><div class="value">${colls.length}</div><div class="label">Collections</div></div>`;
    html += `<div class="stat-card liquid-card-btn"><div class="value">${fmtNum(totalDocs)}</div><div class="label">Total Documents</div></div>`;

    const key = ['users', 'companies', 'documents', 'chat_sessions', 'chat_messages', 'token_usage'];
    for (const k of key) {
      const c = colls.find(c => c.name === k);
      if (c) {
        html += `<div class="stat-card liquid-card-btn"><div class="value">${fmtNum(c.count)}</div><div class="label">${esc(c.name)}</div></div>`;
      }
    }
    html += '</div>';

    html += '<div class="liquid-card"><h3>All Collections</h3>';
    html += renderTable(
      [
        { label: 'Collection', key: 'name', render: r => `<strong>${esc(r.name)}</strong>` },
        { label: 'Documents', key: 'count', render: r => fmtNum(r.count) },
      ],
      colls,
      r => `<button class="btn-ghost btn-sm" onclick="navigateTo('collections'); setTimeout(() => window._browseCollection && window._browseCollection('${esc(r.name)}'), 100)">Browse</button>`
    );
    html += '</div>';

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
  }
});
