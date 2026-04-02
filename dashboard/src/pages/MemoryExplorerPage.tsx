import { useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/hooks/useAsync';
import {
  Section,
  Spinner,
  ErrorDisplay,
  Badge,
  EmptyState,
} from '@/components/ui';
import { Search, Plus, Trash2, Database, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Memory } from '@/types/api';

const PAGE_SIZE = 20;

export function MemoryExplorerPage() {
  const [search, setSearch] = useState('');
  const [namespace, setNamespace] = useState('');
  const [page, setPage] = useState(0);
  const [showAdd, setShowAdd] = useState(false);

  const nsResult = useAsync(() => api.namespaces(), []);

  const memoriesResult = useAsync(
    () =>
      search.length > 1
        ? api.search(search).then((r) => ({ memories: r.results, total: r.results.length }))
        : api.memories({
            namespace: namespace || undefined,
            limit: PAGE_SIZE,
            offset: page * PAGE_SIZE,
          }),
    [search, namespace, page]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (!confirm(`Delete memory ${id.slice(0, 8)}…?`)) return;
      await api.deleteMemory(id);
      memoriesResult.refetch();
    },
    [memoriesResult]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Memory Explorer</h1>
          <p className="text-sm text-gray-400">Browse, search, and manage memories</p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 rounded-lg bg-memoria-700 px-4 py-2 text-sm font-medium text-white hover:bg-memoria-600 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Memory
        </button>
      </div>

      {/* Add Form */}
      {showAdd && <AddMemoryForm onDone={() => { setShowAdd(false); memoriesResult.refetch(); }} />}

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search memories…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            className="w-full rounded-lg border border-gray-800 bg-gray-900/60 py-2.5 pl-10 pr-4 text-sm text-white placeholder-gray-500 focus:border-memoria-700 focus:outline-none focus:ring-1 focus:ring-memoria-700"
          />
        </div>
        <select
          value={namespace}
          onChange={(e) => { setNamespace(e.target.value); setPage(0); }}
          className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2.5 text-sm text-gray-300 focus:border-memoria-700 focus:outline-none"
        >
          <option value="">All Namespaces</option>
          {nsResult.data?.map((ns) => (
            <option key={ns.name} value={ns.name}>
              {ns.name} ({ns.count})
            </option>
          ))}
        </select>
      </div>

      {/* Memories List */}
      {memoriesResult.status === 'loading' ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : memoriesResult.status === 'error' ? (
        <ErrorDisplay error={memoriesResult.error} onRetry={memoriesResult.refetch} />
      ) : memoriesResult.data?.memories.length === 0 ? (
        <EmptyState message="No memories found" icon={<Database className="h-10 w-10" />} />
      ) : (
        <Section title={`Results (${memoriesResult.data?.total ?? 0})`}>
          <div className="space-y-2">
            {memoriesResult.data?.memories.map((mem) => (
              <MemoryCard key={mem.id} memory={mem} onDelete={handleDelete} />
            ))}
          </div>

          {/* Pagination */}
          {!search && (memoriesResult.data?.total ?? 0) > PAGE_SIZE && (
            <div className="flex items-center justify-center gap-3 pt-4">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="rounded-lg border border-gray-800 p-2 text-gray-400 hover:text-white disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-sm text-gray-400">
                Page {page + 1} of {Math.ceil((memoriesResult.data?.total ?? 0) / PAGE_SIZE)}
              </span>
              <button
                disabled={(page + 1) * PAGE_SIZE >= (memoriesResult.data?.total ?? 0)}
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg border border-gray-800 p-2 text-gray-400 hover:text-white disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </Section>
      )}
    </div>
  );
}

function MemoryCard({ memory, onDelete }: { memory: Memory; onDelete: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4 hover:border-gray-700 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Badge variant="info">{memory.namespace || 'default'}</Badge>
            {memory.memory_type && <Badge>{memory.memory_type}</Badge>}
            <span className="text-[10px] text-gray-600 font-mono">{memory.id.slice(0, 12)}</span>
          </div>
          <p
            className={`text-sm text-gray-300 ${expanded ? '' : 'line-clamp-2'} cursor-pointer`}
            onClick={() => setExpanded(!expanded)}
          >
            {memory.content}
          </p>
          <p className="mt-1.5 text-[10px] text-gray-600">
            {new Date(memory.created_at).toLocaleString()}
            {memory.user_id && ` · ${memory.user_id}`}
          </p>
        </div>
        <button
          onClick={() => onDelete(memory.id)}
          className="flex-shrink-0 rounded-md p-1.5 text-gray-600 hover:bg-red-950/50 hover:text-red-400 transition-colors"
          title="Delete memory"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

function AddMemoryForm({ onDone }: { onDone: () => void }) {
  const [content, setContent] = useState('');
  const [ns, setNs] = useState('');
  const [memType, setMemType] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setSaving(true);
    try {
      await api.createMemory({
        content: content.trim(),
        namespace: ns || undefined,
        memory_type: memType || undefined,
      });
      onDone();
    } catch {
      alert('Failed to create memory');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-memoria-800/50 bg-memoria-950/20 p-5 space-y-4"
    >
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Memory content…"
        rows={3}
        className="w-full rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-sm text-white placeholder-gray-500 focus:border-memoria-700 focus:outline-none resize-none"
      />
      <div className="flex gap-3">
        <input
          type="text"
          value={ns}
          onChange={(e) => setNs(e.target.value)}
          placeholder="Namespace (optional)"
          className="flex-1 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-memoria-700 focus:outline-none"
        />
        <select
          value={memType}
          onChange={(e) => setMemType(e.target.value)}
          className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-300 focus:border-memoria-700 focus:outline-none"
        >
          <option value="">Type (auto)</option>
          <option value="user">User</option>
          <option value="feedback">Feedback</option>
          <option value="project">Project</option>
          <option value="reference">Reference</option>
        </select>
        <button
          type="submit"
          disabled={saving || !content.trim()}
          className="rounded-lg bg-memoria-700 px-6 py-2 text-sm font-medium text-white hover:bg-memoria-600 disabled:opacity-40 transition-colors"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
