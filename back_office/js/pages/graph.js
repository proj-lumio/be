/* ── Knowledge Graph page ── */

// ── Force Graph Engine ──
const GRAPH_COLORS = {
  company: '#7966ff', document: '#22cfff', categoria: '#e84393',
  PERSON: '#0984e3', ORGANIZATION: '#e17055', LOCATION: '#fdcb6e',
  PRODUCT: '#00cec9', EVENT: '#fd79a8', CONCEPT: '#a29bfe',
  METRIC: '#55efc4', DATE: '#fab1a0', UNKNOWN: '#a29bfe',
};
const GRAPH_RADIUS = { company: 22, document: 14, categoria: 16, entity: 10 };

function graphColor(n) {
  if (n.group === 'company') return GRAPH_COLORS.company;
  if (n.group === 'document') return GRAPH_COLORS.document;
  if (n.group === 'categoria') return GRAPH_COLORS.categoria;
  return GRAPH_COLORS[n.type] || GRAPH_COLORS.UNKNOWN;
}
function graphRadius(n) { return GRAPH_RADIUS[n.group] || GRAPH_RADIUS.entity; }

function createGraphInstance(canvasId, tooltipId) {
  const state = { nodes: [], edges: [], transform: {x:0,y:0,s:1}, drag: null, hover: null, animId: null, alpha: 1, tick: 0 };

  function load(data) {
    if (state.animId) cancelAnimationFrame(state.animId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return { nodes: 0, edges: 0 };
    const W = canvas.width, H = canvas.height;
    const cx = W / 2, cy = H / 2;
    const spread = data.nodes.length > 40 ? 1.8 : 1;
    state.nodes = data.nodes.map(n => ({
      ...n, x: cx + (Math.random()-0.5)*400*spread, y: cy + (Math.random()-0.5)*300*spread,
      vx: 0, vy: 0, r: graphRadius(n), color: graphColor(n),
    }));
    state.nodes.filter(n => n.group === 'company').forEach(cn => { cn.x = cx; cn.y = cy; });
    state.edges = data.edges.map(e => ({
      ...e,
      sourceNode: state.nodes.find(n => n.id === e.source),
      targetNode: state.nodes.find(n => n.id === e.target),
    })).filter(e => e.sourceNode && e.targetNode);
    state.transform = {x:0,y:0,s:1};
    state.alpha = 1; state.tick = 0;
    animate();
    return { nodes: state.nodes.length, edges: state.edges.length };
  }

  function simStep() {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const N = state.nodes.length;
    state.alpha = Math.max(state.alpha * 0.992, 0.15);
    state.tick++;
    const k = 0.03, repulse = N > 40 ? 20000 : 12000, damp = 0.82;
    const center = {x: cx, y: cy};
    const gravity = N > 40 ? 0.002 : 0.008;
    const edgeLen = N > 40 ? 180 : 110, stiffDrag = 0.6;
    const maxV = 6, alpha = state.alpha;
    for (let i = 0; i < N; i++) {
      for (let j = i+1; j < N; j++) {
        let dx = state.nodes[j].x - state.nodes[i].x, dy = state.nodes[j].y - state.nodes[i].y;
        let d2 = dx*dx + dy*dy || 1, d = Math.sqrt(d2);
        const minDist = state.nodes[i].r + state.nodes[j].r + 8;
        let f = repulse / d2 * alpha;
        if (d < minDist) f += (minDist - d) * 1.5 * alpha;
        let fx = dx / d * f, fy = dy / d * f;
        state.nodes[i].vx -= fx; state.nodes[i].vy -= fy;
        state.nodes[j].vx += fx; state.nodes[j].vy += fy;
      }
    }
    for (const e of state.edges) {
      let dx = e.targetNode.x - e.sourceNode.x, dy = e.targetNode.y - e.sourceNode.y;
      let d = Math.sqrt(dx*dx + dy*dy) || 1;
      let kk = (state.drag && (state.drag.node === e.sourceNode || state.drag.node === e.targetNode)) ? stiffDrag : k;
      let f = (d - edgeLen) * kk * alpha, fx = dx/d * f, fy = dy/d * f;
      e.sourceNode.vx += fx; e.sourceNode.vy += fy;
      e.targetNode.vx -= fx; e.targetNode.vy -= fy;
    }
    for (const n of state.nodes) {
      n.vx += (center.x - n.x) * gravity;
      n.vy += (center.y - n.y) * gravity;
      if (state.drag && state.drag.node === n) { n.vx = 0; n.vy = 0; continue; }
      n.vx *= damp; n.vy *= damp;
      const speed = Math.sqrt(n.vx*n.vx + n.vy*n.vy);
      if (speed > maxV) { n.vx = n.vx/speed*maxV; n.vy = n.vy/speed*maxV; }
      n.x += n.vx; n.y += n.vy;
    }
  }

  function draw() {
    const canvas = document.getElementById(canvasId);
    if (!canvas) { if (state.animId) cancelAnimationFrame(state.animId); state.animId = null; return; }
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.translate(state.transform.x, state.transform.y);
    ctx.scale(state.transform.s, state.transform.s);
    const borderColor = 'rgba(255,255,255,0.25)';
    const textColor = '#ffffff';
    ctx.lineWidth = 1.5;
    for (const e of state.edges) {
      ctx.strokeStyle = borderColor; ctx.globalAlpha = 0.7;
      ctx.beginPath(); ctx.moveTo(e.sourceNode.x, e.sourceNode.y); ctx.lineTo(e.targetNode.x, e.targetNode.y); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    for (const n of state.nodes) {
      ctx.fillStyle = n.color; ctx.shadowColor = n.color;
      ctx.shadowBlur = n === state.hover ? 16 : 6;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r * (n === state.hover ? 1.25 : 1), 0, Math.PI*2); ctx.fill();
      ctx.shadowBlur = 0;
      const fontSize = n.group === 'company' ? 11 : n.group === 'document' || n.group === 'categoria' ? 9 : 8;
      ctx.font = `${n.group==='company'||n.group==='categoria'?'bold ':''}${fontSize}px 'Segoe UI',system-ui,sans-serif`;
      ctx.fillStyle = textColor; ctx.textAlign = 'center';
      const label = n.label.length > 20 ? n.label.slice(0,18)+'..' : n.label;
      ctx.fillText(label, n.x, n.y + n.r + fontSize + 2);
    }
    ctx.restore();
  }

  function animate() { simStep(); draw(); state.animId = requestAnimationFrame(animate); }

  function initInteraction() {
    const c = document.getElementById(canvasId);
    if (!c) return;
    let panStart = null;
    function toGraph(ex, ey) {
      const r = c.getBoundingClientRect(), sx = c.width/r.width, sy = c.height/r.height;
      return { x: ((ex-r.left)*sx - state.transform.x)/state.transform.s, y: ((ey-r.top)*sy - state.transform.y)/state.transform.s };
    }
    function findNode(gx, gy) {
      for (let i = state.nodes.length-1; i >= 0; i--) { const n = state.nodes[i]; if ((gx-n.x)**2+(gy-n.y)**2 <= (n.r+4)**2) return n; }
      return null;
    }
    c.addEventListener('mousedown', e => {
      const g = toGraph(e.clientX, e.clientY), n = findNode(g.x, g.y);
      if (n) { state.drag = {node:n, ox:n.x-g.x, oy:n.y-g.y}; c.style.cursor='grabbing'; }
      else { panStart = {mx:e.clientX, my:e.clientY, tx:state.transform.x, ty:state.transform.y}; }
    });
    c.addEventListener('mousemove', e => {
      const g = toGraph(e.clientX, e.clientY);
      if (state.drag) { state.drag.node.x=g.x+state.drag.ox; state.drag.node.y=g.y+state.drag.oy; state.drag.node.vx=0; state.drag.node.vy=0; return; }
      if (panStart) { state.transform.x=panStart.tx+(e.clientX-panStart.mx); state.transform.y=panStart.ty+(e.clientY-panStart.my); return; }
      const n = findNode(g.x, g.y); state.hover = n; c.style.cursor = n ? 'pointer' : 'grab';
      const tip = document.getElementById(tooltipId);
      if (n) {
        const rect = c.getBoundingClientRect(); tip.style.display='block';
        tip.style.left=(e.clientX-rect.left+14)+'px'; tip.style.top=(e.clientY-rect.top-10)+'px';
        let html = `<strong>${esc(n.label)}</strong><br><span style="color:var(--muted-foreground)">${n.group}`;
        if (n.type) html += ` (${n.type})`; html += '</span>';
        if (n.description) html += `<br>${esc(n.description)}`;
        html += `<br><span style="color:var(--muted-foreground)">${state.edges.filter(e=>e.sourceNode===n||e.targetNode===n).length} connection(s)</span>`;
        tip.innerHTML = html;
      } else { tip.style.display='none'; }
    });
    c.addEventListener('mouseup', () => { state.drag=null; panStart=null; c.style.cursor='grab'; });
    c.addEventListener('mouseleave', () => { state.drag=null; panStart=null; state.hover=null; const t=document.getElementById(tooltipId); if(t) t.style.display='none'; });
    c.addEventListener('wheel', e => { e.preventDefault(); const f=e.deltaY<0?1.1:0.9; state.transform.s=Math.max(0.2,Math.min(5,state.transform.s*f)); }, {passive:false});
  }

  return { load, initInteraction, zoom(f){ state.transform.s=Math.max(0.2,Math.min(5,state.transform.s*f)); }, reset(){ state.transform={x:0,y:0,s:1}; } };
}

// ── Page ──
let _graphInstance = null;

registerPage('graph', async (container) => {
  // Load companies for the selector
  let companies = [];
  try {
    const d = await boApi('/backoffice/collections/companies/documents?skip=0&limit=200');
    companies = d.items;
  } catch {}

  const companyOpts = companies.map(c =>
    `<option value="${esc(c._id)}">${esc(c.ragione_sociale || c.name)}</option>`
  ).join('');

  const legendItems = [
    { label: 'Company', color: GRAPH_COLORS.company },
    { label: 'Document', color: GRAPH_COLORS.document },
    { label: 'Category', color: GRAPH_COLORS.categoria },
    { label: 'Person', color: GRAPH_COLORS.PERSON },
    { label: 'Organization', color: GRAPH_COLORS.ORGANIZATION },
    { label: 'Location', color: GRAPH_COLORS.LOCATION },
    { label: 'Other', color: GRAPH_COLORS.UNKNOWN },
  ];

  container.innerHTML = `
    <div class="liquid-card" style="padding:14px">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <h3 style="margin:0">Knowledge Graph</h3>
        <select id="graph-mode" onchange="window._toggleGraphMode()" style="padding:8px 12px;background:rgba(255,255,255,0.06);border:1px solid var(--border);border-radius:12px;color:var(--foreground);font-size:13px">
          <option value="company">Single Company</option>
          <option value="national">National Graph</option>
        </select>
        <select id="graph-company" style="padding:8px 12px;background:rgba(255,255,255,0.06);border:1px solid var(--border);border-radius:12px;color:var(--foreground);font-size:13px;min-width:200px">
          ${companyOpts || '<option>No companies</option>'}
        </select>
        <span id="graph-stats" style="font-size:12px;color:var(--muted-foreground)"></span>
        <div style="margin-left:auto;display:flex;gap:6px;align-items:center">
          <button class="btn-outline btn-sm" onclick="window._graphZoom(1.3)">+</button>
          <button class="btn-outline btn-sm" onclick="window._graphZoom(0.7)">-</button>
          <button class="btn-outline btn-sm" onclick="window._graphReset()">Reset</button>
        </div>
      </div>
    </div>
    <div class="liquid-card" style="padding:0;overflow:hidden;position:relative;margin-top:0">
      <canvas id="graph-canvas" width="1160" height="600" style="width:100%;display:block;cursor:grab;background:var(--background)"></canvas>
      <div id="graph-tooltip" style="display:none;position:absolute;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:10px 14px;font-size:12px;pointer-events:none;max-width:280px;z-index:10"></div>
      <div style="position:absolute;bottom:12px;left:12px;display:flex;gap:14px;font-size:11px;color:var(--muted-foreground)">
        ${legendItems.map(l => `<span><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${l.color};vertical-align:middle"></span> ${l.label}</span>`).join('')}
      </div>
    </div>`;

  // Init graph
  _graphInstance = createGraphInstance('graph-canvas', 'graph-tooltip');
  _graphInstance.initInteraction();

  window._toggleGraphMode = () => {
    const mode = document.getElementById('graph-mode').value;
    document.getElementById('graph-company').style.display = mode === 'company' ? '' : 'none';
    window._loadGraph();
  };

  document.getElementById('graph-company').addEventListener('change', () => window._loadGraph());

  window._loadGraph = async () => {
    const mode = document.getElementById('graph-mode').value;
    const stats = document.getElementById('graph-stats');
    stats.textContent = 'Loading...';
    try {
      let data;
      if (mode === 'national') {
        data = await boApi('/backoffice/graph/national');
      } else {
        const cid = document.getElementById('graph-company')?.value;
        if (!cid) { stats.textContent = 'Select a company'; return; }
        data = await boApi(`/backoffice/graph/${cid}`);
      }
      const s = _graphInstance.load(data);
      _graphInstance.initInteraction();
      stats.textContent = `${s.nodes} nodes, ${s.edges} edges`;
    } catch (e) { stats.textContent = `Error: ${esc(e.message)}`; }
  };

  window._graphZoom = (f) => { if (_graphInstance) _graphInstance.zoom(f); };
  window._graphReset = () => { if (_graphInstance) _graphInstance.reset(); };

  // Auto-load national graph on page open
  window._loadGraph();
});
