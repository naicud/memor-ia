/* Memoria Dashboard — Single-Page Application */

const API = '/api/v1';
const app = document.getElementById('app');
const statusBadge = document.getElementById('status-badge');

// ─── API Client ──────────────────────────────────────────
async function api(path, options = {}) {
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    return await res.json();
  } catch (e) {
    return { error: e.message };
  }
}

// ─── Health Check ────────────────────────────────────────
async function checkHealth() {
  const data = await api('/health');
  if (data.status === 'ok') {
    statusBadge.textContent = `✓ v${data.version} — ${Math.round(data.uptime_seconds)}s uptime`;
    statusBadge.className = 'ml-auto text-sm text-green-400';
  } else {
    statusBadge.textContent = '✗ disconnected';
    statusBadge.className = 'ml-auto text-sm text-red-400';
  }
}

// ─── Router ──────────────────────────────────────────────
const routes = {
  '/': renderOverview,
  '/memories': renderMemories,
  '/graph': renderGraph,
  '/audit': renderAudit,
  '/settings': renderSettings,
};

function navigate() {
  const hash = location.hash.replace('#', '') || '/';
  const render = routes[hash] || renderOverview;
  document.querySelectorAll('.nav-link').forEach(el => {
    const page = el.dataset.page;
    const target = page === 'overview' ? '/' : `/${page}`;
    el.classList.toggle('active', hash === target);
  });
  render();
}

window.addEventListener('hashchange', navigate);

// ─── Overview Page ───────────────────────────────────────
async function renderOverview() {
  app.innerHTML = '<div class="text-gray-500">Loading…</div>';
  const [health, stats, namespaces] = await Promise.all([
    api('/health'),
    api('/stats'),
    api('/namespaces'),
  ]);

  const nsCount = stats.namespace_count || 0;
  const memCount = stats.total_memories || 0;
  const plugCount = stats.plugin_count || 0;
  const attCount = stats.attachments?.total_attachments || 0;

  app.innerHTML = `
    <h1 class="text-2xl font-bold mb-6">📊 Overview</h1>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
      <div class="metric-card"><div class="metric-value">${memCount}</div><div class="metric-label">Memories</div></div>
      <div class="metric-card"><div class="metric-value">${nsCount}</div><div class="metric-label">Namespaces</div></div>
      <div class="metric-card"><div class="metric-value">${plugCount}</div><div class="metric-label">Plugins</div></div>
      <div class="metric-card"><div class="metric-value">${attCount}</div><div class="metric-label">Attachments</div></div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="card">
        <h2 class="text-lg font-semibold mb-3">Namespaces</h2>
        <div id="ns-list">${renderNamespaceList(namespaces.namespaces || [])}</div>
      </div>
      <div class="card">
        <h2 class="text-lg font-semibold mb-3">System</h2>
        <div class="space-y-2 text-sm">
          <div><span class="text-gray-400">Status:</span> <span class="text-green-400">${health.status || 'unknown'}</span></div>
          <div><span class="text-gray-400">Version:</span> ${health.version || 'unknown'}</div>
          <div><span class="text-gray-400">Uptime:</span> ${formatUptime(health.uptime_seconds)}</div>
          <div><span class="text-gray-400">Disk (attachments):</span> ${formatBytes(stats.attachments?.disk_usage_bytes || 0)}</div>
        </div>
      </div>
    </div>
  `;
}

function renderNamespaceList(namespaces) {
  if (!namespaces.length) return '<div class="text-gray-500 text-sm">No namespaces found</div>';
  return namespaces.map(ns => {
    const name = typeof ns === 'string' ? ns : ns.name || ns;
    return `<div class="flex items-center gap-2 py-1"><span class="w-2 h-2 rounded-full bg-purple-400"></span><span>${name}</span></div>`;
  }).join('');
}

// ─── Memories Page ───────────────────────────────────────
async function renderMemories() {
  app.innerHTML = `
    <h1 class="text-2xl font-bold mb-6">🧠 Memory Explorer</h1>
    <div class="flex gap-4 mb-6">
      <input type="text" id="search-input" class="input flex-1" placeholder="Search memories…">
      <button id="search-btn" class="btn-primary">Search</button>
    </div>
    <div id="memory-results" class="space-y-3"></div>
  `;

  document.getElementById('search-btn').onclick = async () => {
    const q = document.getElementById('search-input').value.trim();
    const results = document.getElementById('memory-results');
    if (!q) { results.innerHTML = '<div class="text-gray-500">Enter a search query</div>'; return; }
    results.innerHTML = '<div class="text-gray-500">Searching…</div>';
    const data = await api(`/search?q=${encodeURIComponent(q)}`);
    if (data.results && data.results.length) {
      results.innerHTML = data.results.map(r => `
        <div class="card"><div class="text-sm">${escapeHtml(r.content || JSON.stringify(r))}</div></div>
      `).join('');
    } else {
      results.innerHTML = '<div class="text-gray-500">No results found</div>';
    }
  };

  document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('search-btn').click();
  });

  const data = await api('/memories');
  const results = document.getElementById('memory-results');
  if (data.memories && data.memories.length) {
    results.innerHTML = `<div class="text-gray-400 text-sm mb-2">${data.total} memories in default namespace</div>` +
      data.memories.map(m => `
        <div class="card"><div class="text-sm">${escapeHtml(m.content || m.id || JSON.stringify(m))}</div></div>
      `).join('');
  } else {
    results.innerHTML = '<div class="text-gray-500">No memories stored yet. Add some via the API!</div>';
  }
}

// ─── Graph Page ──────────────────────────────────────────
async function renderGraph() {
  app.innerHTML = `
    <h1 class="text-2xl font-bold mb-6">🕸️ Knowledge Graph</h1>
    <div id="graph-container"></div>
  `;

  const data = await api('/graph');
  if (!data.nodes || !data.nodes.length) {
    document.getElementById('graph-container').innerHTML =
      '<div class="flex items-center justify-center h-96 text-gray-500">No graph data. Add memories with namespaces to see the graph.</div>';
    return;
  }

  renderD3Graph(data);
}

function renderD3Graph(data) {
  const container = document.getElementById('graph-container');
  const width = container.clientWidth;
  const height = 500;

  const svg = d3.select(container).append('svg')
    .attr('width', width)
    .attr('height', height);

  const simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2));

  const link = svg.append('g').selectAll('line')
    .data(data.edges).join('line').attr('class', 'link');

  const node = svg.append('g').selectAll('circle')
    .data(data.nodes).join('circle')
    .attr('r', d => d.size || 8)
    .attr('class', d => `node-${d.type}`)
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

  const label = svg.append('g').selectAll('text')
    .data(data.nodes).join('text')
    .text(d => d.label)
    .attr('font-size', d => d.type === 'namespace' ? 12 : 9)
    .attr('fill', '#9ca3af')
    .attr('dx', 12).attr('dy', 4);

  node.append('title').text(d => d.content || d.label);

  simulation.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('cx', d => d.x).attr('cy', d => d.y);
    label.attr('x', d => d.x).attr('y', d => d.y);
  });
}

// ─── Audit Page ──────────────────────────────────────────
async function renderAudit() {
  app.innerHTML = '<h1 class="text-2xl font-bold mb-6">📋 Audit Log</h1><div id="audit-content" class="text-gray-500">Loading…</div>';
  const data = await api('/audit?limit=100');
  const el = document.getElementById('audit-content');

  if (data.entries && data.entries.length) {
    el.innerHTML = `
      <table class="table"><thead><tr><th>Time</th><th>Action</th><th>Details</th></tr></thead>
      <tbody>${data.entries.map(e => `
        <tr><td class="text-gray-400">${e.timestamp || '—'}</td><td>${e.action || e.type || '—'}</td>
        <td class="text-gray-400 truncate max-w-md">${escapeHtml(e.details || e.summary || JSON.stringify(e))}</td></tr>
      `).join('')}</tbody></table>`;
  } else {
    el.innerHTML = '<div class="text-gray-500">No audit entries yet</div>';
  }
}

// ─── Settings Page ───────────────────────────────────────
async function renderSettings() {
  const [plugins, streams] = await Promise.all([api('/plugins'), api('/streams')]);
  app.innerHTML = `
    <h1 class="text-2xl font-bold mb-6">⚙️ Settings</h1>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div class="card">
        <h2 class="text-lg font-semibold mb-3">Plugins</h2>
        ${(plugins.plugins || []).length ? plugins.plugins.map(p => `
          <div class="flex items-center gap-2 py-1">
            <span class="w-2 h-2 rounded-full ${p.active ? 'bg-green-400' : 'bg-gray-500'}"></span>
            <span>${p.name || p}</span>
          </div>
        `).join('') : '<div class="text-gray-500 text-sm">No plugins loaded</div>'}
      </div>
      <div class="card">
        <h2 class="text-lg font-semibold mb-3">Streams</h2>
        <pre class="text-xs text-gray-400 overflow-auto">${JSON.stringify(streams.streams || {}, null, 2)}</pre>
      </div>
    </div>
  `;
}

// ─── Helpers ─────────────────────────────────────────────
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function formatUptime(seconds) {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(1)} ${units[i]}`;
}

// ─── Boot ────────────────────────────────────────────────
checkHealth();
setInterval(checkHealth, 30000);
navigate();
