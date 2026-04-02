# Dashboard — React Frontend

The Memoria Dashboard is a modern React SPA providing real-time visualization and management of the memory system.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Pages](#pages)
- [Architecture](#architecture)
- [Development](#development)
- [Production Build](#production-build)
- [API Endpoints](#api-endpoints)
- [Component Reference](#component-reference)

---

## Overview

The dashboard replaces the original vanilla JS frontend with a full React + TypeScript application built on Vite. It connects to the existing Python backend REST API on `/api/v1/` and provides 5 pages for monitoring, exploring, and managing memories.

**Features:**
- 📊 Real-time stats with auto-refresh polling
- 🔍 Full-text memory search with namespace filtering
- ✏️ Memory CRUD (create, read, delete)
- 🕸️ Interactive force-directed knowledge graph (canvas-based)
- 📋 Filterable/paginated audit log
- 🔌 Plugin and stream monitoring
- 🌙 Dark theme with custom Memoria color palette

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React | 19.x |
| Language | TypeScript | 5.8+ |
| Build Tool | Vite | 6.x |
| Styling | Tailwind CSS | 3.4+ |
| Charts | Recharts | 2.x |
| Icons | Lucide React | 0.487+ |
| Routing | React Router DOM | 7.x |
| Utilities | clsx | 2.x |

---

## Pages

### 1. Overview (`/`)

System health dashboard with:
- **Stat cards**: Total memories, namespaces, attachments, plugins
- **Bar chart**: Memories per namespace (Recharts)
- **Pie chart**: Namespace distribution
- **System status**: Version, uptime, health check
- Auto-refreshes every 10-15 seconds

### 2. Memory Explorer (`/memories`)

Full memory management interface:
- **Search**: Real-time search across all memories
- **Namespace filter**: Dropdown to filter by namespace
- **Pagination**: 20 items per page with prev/next controls
- **Add Memory**: Form with content, namespace, and memory type
- **Delete**: Per-memory delete with confirmation dialog
- **Memory cards**: Expandable content, badges for namespace/type, timestamps

### 3. Knowledge Graph (`/graph`)

Interactive visualization of memory relationships:
- **Canvas-based**: Custom force-directed simulation (no heavy library dependency)
- **Node types**: Color-coded by type (namespace=blue, memory=indigo, entity=purple, concept=amber)
- **Hover tooltips**: Node details on hover
- **Legend**: Type color reference
- **Refresh**: Manual refresh button

### 4. Audit Log (`/audit`)

Operations audit trail:
- **Action filtering**: Dropdown to filter by action type (create, delete, update, etc.)
- **Limit control**: Last 50/100/500 entries
- **Paginated table**: 30 rows per page
- **Color-coded badges**: Green for create, red for delete, amber for update
- **Columns**: Timestamp, Action, Details, User, Namespace

### 5. Settings (`/settings`)

System configuration and monitoring:
- **System info**: Version, status, uptime
- **Plugins**: Card grid with name, version, enabled/disabled status, description
- **Event streams**: Table with stream name, length, consumers, last entry ID

---

## Architecture

```
dashboard/
├── index.html                  # Vite entry HTML
├── package.json                # Dependencies & scripts
├── vite.config.ts              # Vite config (proxy + build output)
├── tsconfig.json               # TypeScript config
├── tailwind.config.js          # Tailwind theme (Memoria palette)
├── postcss.config.js           # PostCSS with Tailwind + Autoprefixer
├── public/
│   └── favicon.svg             # Memoria brain icon
└── src/
    ├── main.tsx                # React entry point
    ├── App.tsx                 # Router configuration
    ├── index.css               # Tailwind directives + scrollbar
    ├── vite-env.d.ts           # Vite type declarations
    ├── types/
    │   └── api.ts              # TypeScript interfaces for all API types
    ├── lib/
    │   └── api.ts              # API client (fetch wrapper for /api/v1/)
    ├── hooks/
    │   └── useAsync.ts         # useAsync + usePolling hooks
    ├── components/
    │   ├── Layout.tsx          # Sidebar + main content layout
    │   └── ui.tsx              # Shared UI: StatCard, Badge, Spinner, etc.
    └── pages/
        ├── OverviewPage.tsx    # Dashboard overview with charts
        ├── MemoryExplorerPage.tsx # Memory CRUD + search
        ├── KnowledgeGraphPage.tsx # Canvas force-directed graph
        ├── AuditLogPage.tsx    # Audit log table
        └── SettingsPage.tsx    # Plugins + streams
```

### Data Flow

```
┌──────────────┐     fetch()     ┌──────────────────┐
│  React SPA   │ ──────────────► │  Python Backend   │
│  (Vite dev   │  /api/v1/*      │  (port 8080)      │
│   port 5173) │ ◄────────────── │  DashboardServer  │
└──────────────┘     JSON        └──────────────────┘
                                         │
                                         ▼
                                 ┌──────────────────┐
                                 │    Memoria Core   │
                                 │  (97 tools/APIs)  │
                                 └──────────────────┘
```

In production, Vite builds to `src/memoria/dashboard/static/` and the Python server serves everything from there (SPA fallback included).

---

## Development

### Prerequisites

- Node.js ≥ 18
- npm ≥ 9
- Python backend running (`memoria.dashboard_start()`)

### Setup

```bash
cd dashboard
npm install
npm run dev
```

This starts Vite dev server on `http://localhost:5173` with hot module replacement. API requests are proxied to `http://127.0.0.1:8080`.

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with HMR |
| `npm run build` | TypeScript check + production build |
| `npm run preview` | Preview production build locally |
| `npm run typecheck` | TypeScript type checking only |
| `npm run lint` | ESLint check |

### Starting the Backend

```python
from memoria import Memoria

m = Memoria()
m.dashboard_start(port=8080)  # Starts REST API server
```

Or via MCP:
```
Tool: start_dashboard
Args: {"port": 8080}
```

---

## Production Build

Build the dashboard for production:

```bash
cd dashboard
npm run build
```

This outputs optimized files to `src/memoria/dashboard/static/`:
- `index.html` — SPA entry
- `assets/index-*.css` — Tailwind CSS (~16KB gzipped: ~4KB)
- `assets/index-*.js` — React bundle (~682KB, gzipped: ~195KB)
- `favicon.svg` — Memoria icon

The Python `DashboardServer` serves these files directly. No separate web server needed.

### SPA Routing

The server handles client-side routing: any non-API, non-static request falls back to `index.html` (see `server.py` line 99-100).

---

## API Endpoints

The dashboard consumes the existing REST API:

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/api/v1/health` | GET | System health check | `{status, version, uptime_seconds}` |
| `/api/v1/stats` | GET | Aggregate statistics | `{namespace_count, total_memories, attachments, plugin_count}` |
| `/api/v1/namespaces` | GET | List all namespaces | `{namespaces: [{name, count}]}` |
| `/api/v1/memories` | GET | List memories | `{memories: [...], total}` |
| `/api/v1/memories` | POST | Create memory | `{created: bool, result}` |
| `/api/v1/memories/{id}` | GET | Get single memory | Memory object |
| `/api/v1/memories/{id}` | DELETE | Delete memory | `{deleted: bool, result}` |
| `/api/v1/search?q=` | GET | Search memories | `{results: [...], query}` |
| `/api/v1/graph` | GET | Knowledge graph data | `{nodes: [...], edges: [...]}` |
| `/api/v1/audit?limit=` | GET | Audit log entries | `{entries: [...], total}` |
| `/api/v1/plugins` | GET | List plugins | `{plugins: [...]}` |
| `/api/v1/streams` | GET | Event stream info | `{streams: {...}}` |

### Query Parameters

- `memories`: `?namespace=X&limit=20&offset=0`
- `search`: `?q=search+terms`
- `audit`: `?limit=100`

---

## Component Reference

### Shared UI (`components/ui.tsx`)

| Component | Props | Description |
|-----------|-------|-------------|
| `StatCard` | `title, value, subtitle?, icon?, className?` | Metric display card |
| `Section` | `title, description?, children, action?` | Section wrapper with title |
| `Badge` | `children, variant?` | Status badge (default/success/warning/error/info) |
| `Spinner` | `size?` | Loading spinner (sm/md/lg) |
| `EmptyState` | `message, icon?` | Empty content placeholder |
| `ErrorDisplay` | `error, onRetry?` | Error message with retry button |

### Hooks (`hooks/useAsync.ts`)

| Hook | Signature | Description |
|------|-----------|-------------|
| `useAsync` | `(fn, deps) → {status, data, error, refetch}` | Async data fetching with state |
| `usePolling` | `(fn, intervalMs, deps) → ...` | Auto-refreshing data (extends useAsync) |

### API Client (`lib/api.ts`)

```typescript
import { api } from '@/lib/api';

// All methods return typed Promises
const health = await api.health();
const memories = await api.memories({ namespace: 'work', limit: 20 });
const results = await api.search('typescript');
const graph = await api.graph();
await api.createMemory({ content: 'Hello', namespace: 'test' });
await api.deleteMemory('memory-id');
```

---

## Theme

Custom Memoria color palette in `tailwind.config.js`:

```
memoria-50:  #f0f4ff  (lightest)
memoria-100: #dbe4ff
memoria-200: #bac8ff
memoria-300: #91a7ff
memoria-400: #748ffc
memoria-500: #5c7cfa  (primary)
memoria-600: #4c6ef5
memoria-700: #4263eb
memoria-800: #3b5bdb
memoria-900: #364fc7
memoria-950: #1e3a8a  (darkest)
```

Fonts: **Inter** (sans-serif), **JetBrains Mono** (monospace)

Background: `gray-950` with `gray-900/40` cards. Borders: `gray-800`.
