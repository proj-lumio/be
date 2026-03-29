registerPage('analytics', async (container) => {
  let skip = 0;
  const limit = 50;

  async function load(s) {
    skip = s || 0;
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi(`/backoffice/collections/token_usage/documents?skip=${skip}&limit=${limit}`);
      let html = '';

      // Summary stats
      let totalTokens = 0, totalCredits = 0, totalRequests = 0;
      for (const item of d.items) {
        totalTokens += item.total_tokens || 0;
        totalCredits += item.credits_used || 0;
        totalRequests += item.request_count || 0;
      }

      html += '<div class="stats-grid">';
      html += `<div class="stat-card liquid-card-btn"><div class="value">${fmtNum(d.total)}</div><div class="label">Total Records</div></div>`;
      html += `<div class="stat-card liquid-card-btn"><div class="value">${fmtNum(totalTokens)}</div><div class="label">Tokens (this page)</div></div>`;
      html += `<div class="stat-card liquid-card-btn"><div class="value">${totalCredits.toFixed(1)}</div><div class="label">Credits (this page)</div></div>`;
      html += `<div class="stat-card liquid-card-btn"><div class="value">${fmtNum(totalRequests)}</div><div class="label">Requests (this page)</div></div>`;
      html += '</div>';

      html += '<div class="liquid-card"><h3>Token Usage Records</h3>';
      html += renderTable(
        [
          { label: 'ID', key: '_id', render: r => `<code style="font-size:11px">${esc(truncate(r._id, 12))}</code>` },
          { label: 'User ID', key: 'user_id', render: r => `<code style="font-size:11px">${esc(truncate(r.user_id, 12))}</code>` },
          { label: 'Endpoint', key: 'endpoint', render: r => `<strong>${esc(r.endpoint)}</strong>` },
          { label: 'Requests', key: 'request_count' },
          { label: 'Prompt', key: 'prompt_tokens', render: r => fmtNum(r.prompt_tokens) },
          { label: 'Completion', key: 'completion_tokens', render: r => fmtNum(r.completion_tokens) },
          { label: 'Total', key: 'total_tokens', render: r => fmtNum(r.total_tokens) },
          { label: 'Credits', key: 'credits_used', render: r => `<span class="badge badge-ok">${(r.credits_used || 0).toFixed(2)}</span>` },
          { label: 'Date', key: 'created_at', render: r => fmtDate(r.created_at) },
        ],
        d.items,
        r => `<button class="btn-destructive btn-sm" onclick="deleteTokenRecord('${r._id}')">Delete</button>`
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateAnalytics');
      html += '</div>';

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  window._paginateAnalytics = load;
  load(0);

  window.deleteTokenRecord = async (id) => {
    if (!confirm('Delete this record?')) return;
    try {
      await boApi(`/backoffice/collections/token_usage/documents/${id}`, { method: 'DELETE' });
      load(skip);
    } catch (e) { alert(e.message); }
  };
});
