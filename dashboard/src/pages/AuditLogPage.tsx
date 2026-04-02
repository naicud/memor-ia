import { useState } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/hooks/useAsync';
import {
  Section,
  Spinner,
  ErrorDisplay,
  Badge,
  EmptyState,
} from '@/components/ui';
import { ScrollText, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZE = 30;

export function AuditLogPage() {
  const [limit, setLimit] = useState(100);
  const [page, setPage] = useState(0);
  const [filterAction, setFilterAction] = useState('');

  const auditResult = useAsync(() => api.audit(limit), [limit]);

  const entries = auditResult.data?.entries ?? [];
  const filtered = filterAction
    ? entries.filter((e) => e.action === filterAction)
    : entries;
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  const uniqueActions = [...new Set(entries.map((e) => e.action))].sort();

  const actionVariant = (action: string) => {
    if (action.includes('create') || action.includes('add')) return 'success' as const;
    if (action.includes('delete') || action.includes('remove')) return 'error' as const;
    if (action.includes('update') || action.includes('modify')) return 'warning' as const;
    return 'default' as const;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Log</h1>
          <p className="text-sm text-gray-400">
            Track all memory operations and changes
          </p>
        </div>
        <button
          onClick={auditResult.refetch}
          className="flex items-center gap-2 rounded-lg border border-gray-800 px-3 py-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <select
          value={filterAction}
          onChange={(e) => { setFilterAction(e.target.value); setPage(0); }}
          className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2.5 text-sm text-gray-300 focus:border-memoria-700 focus:outline-none"
        >
          <option value="">All Actions</option>
          {uniqueActions.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          value={limit}
          onChange={(e) => { setLimit(Number(e.target.value)); setPage(0); }}
          className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2.5 text-sm text-gray-300 focus:border-memoria-700 focus:outline-none"
        >
          <option value={50}>Last 50</option>
          <option value={100}>Last 100</option>
          <option value={500}>Last 500</option>
        </select>
      </div>

      {/* Content */}
      {auditResult.status === 'loading' ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : auditResult.status === 'error' ? (
        <ErrorDisplay error={auditResult.error} onRetry={auditResult.refetch} />
      ) : filtered.length === 0 ? (
        <EmptyState message="No audit entries" icon={<ScrollText className="h-10 w-10" />} />
      ) : (
        <Section title={`${filtered.length} entries`}>
          <div className="overflow-hidden rounded-xl border border-gray-800">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60">
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Timestamp
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Action
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Details
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    User
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Namespace
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((entry, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-800/50 hover:bg-gray-900/30 transition-colors"
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-gray-500">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={actionVariant(entry.action)}>{entry.action}</Badge>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 text-gray-300">
                      {entry.details}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{entry.user_id || '—'}</td>
                    <td className="px-4 py-3 text-gray-500">{entry.namespace || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-4">
              <button
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
                className="rounded-lg border border-gray-800 p-2 text-gray-400 hover:text-white disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="text-sm text-gray-400">
                Page {page + 1} of {totalPages}
              </span>
              <button
                disabled={page + 1 >= totalPages}
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
