registerPage('chat-sessions', async (container) => {
  let skip = 0;
  const limit = 50;

  async function load(s) {
    skip = s || 0;
    container.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading...</div>';
    try {
      const d = await boApi(`/backoffice/collections/chat_sessions/documents?skip=${skip}&limit=${limit}`);
      let html = '';

      html += '<div class="liquid-card"><h3>Chat Sessions</h3>';
      html += renderTable(
        [
          { label: 'ID', key: '_id', render: r => `<code style="font-size:11px">${esc(r._id)}</code>` },
          { label: 'Title', key: 'title', render: r => `<strong>${esc(r.title)}</strong>` },
          { label: 'Scope', key: 'scope', render: r => `<span class="badge badge-pending">${esc(r.scope || 'company')}</span>` },
          { label: 'User ID', key: 'user_id', render: r => `<code style="font-size:11px">${esc(truncate(r.user_id, 12))}</code>` },
          { label: 'Company ID', key: 'company_id', render: r => r.company_id ? `<code style="font-size:11px">${esc(truncate(r.company_id, 12))}</code>` : '-' },
          { label: 'Created', key: 'created_at', render: r => fmtDate(r.created_at) },
        ],
        d.items,
        r => `
          <button class="btn-ghost btn-sm" onclick="viewSessionMessages('${r._id}')">Messages</button>
          <button class="btn-ghost btn-sm" onclick="viewSessionJson('${r._id}')">JSON</button>
          <button class="btn-destructive btn-sm" onclick="deleteSession('${r._id}')">Delete</button>
        `
      );
      html += renderPagination(d.total, skip, limit, 'window._paginateSessions');
      html += '</div>';

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="liquid-card"><p style="color:var(--destructive)">Error: ${esc(e.message)}</p></div>`;
    }
  }

  window._paginateSessions = load;
  load(0);

  window.viewSessionJson = async (id) => {
    try {
      const doc = await boApi(`/backoffice/collections/chat_sessions/documents/${id}`);
      openModal('Session Detail', `<div class="json-view">${esc(JSON.stringify(doc, null, 2))}</div>`);
    } catch (e) { alert(e.message); }
  };

  window.viewSessionMessages = async (sessionId) => {
    try {
      const d = await boApi(`/backoffice/collections/chat_messages/documents?skip=0&limit=200`);
      const msgs = d.items.filter(m => m.session_id === sessionId);
      if (!msgs.length) {
        openModal('Messages', '<div class="empty-state">No messages in this session</div>');
        return;
      }
      let body = '<div style="display:flex;flex-direction:column;gap:10px">';
      for (const m of msgs) {
        const isUser = m.role === 'user';
        body += `<div style="padding:10px 14px;border-radius:12px;max-width:90%;
          ${isUser ? 'align-self:flex-end;background:var(--primary);color:#fff' : 'align-self:flex-start;background:rgba(255,255,255,0.06);border:1px solid var(--border)'};
          font-size:13px;line-height:1.5">
          <div style="font-size:10px;color:${isUser ? 'rgba(255,255,255,0.7)' : 'var(--muted-foreground)'};margin-bottom:4px">${esc(m.role)} · ${fmtDate(m.created_at)}</div>
          ${esc(truncate(m.content, 500))}
          ${m.tokens_used ? `<div style="font-size:10px;margin-top:4px;color:${isUser ? 'rgba(255,255,255,0.5)' : 'var(--muted-foreground)'}">${m.tokens_used} tokens</div>` : ''}
        </div>`;
      }
      body += '</div>';
      openModal(`Messages (${msgs.length})`, body);
    } catch (e) { alert(e.message); }
  };

  window.deleteSession = async (id) => {
    if (!confirm('Delete this session?')) return;
    try {
      await boApi(`/backoffice/collections/chat_sessions/documents/${id}`, { method: 'DELETE' });
      load(skip);
    } catch (e) { alert(e.message); }
  };
});
