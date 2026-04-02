import { api } from '@/lib/api';
import { useAsync } from '@/hooks/useAsync';
import {
  Section,
  Spinner,
  ErrorDisplay,
  Badge,
  EmptyState,
} from '@/components/ui';
import { Puzzle, Radio, RefreshCw } from 'lucide-react';

export function SettingsPage() {
  const pluginsResult = useAsync(() => api.plugins(), []);
  const streamsResult = useAsync(() => api.streams(), []);
  const healthResult = useAsync(() => api.health(), []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-400">System configuration and monitoring</p>
      </div>

      {/* System Info */}
      <Section title="System Information" description="Current runtime configuration">
        {healthResult.status === 'loading' ? (
          <Spinner />
        ) : healthResult.status === 'error' ? (
          <ErrorDisplay error={healthResult.error} onRetry={healthResult.refetch} />
        ) : (
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-gray-500">Version</p>
                <p className="mt-1 text-lg font-semibold text-white">
                  {healthResult.data?.version}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-gray-500">Status</p>
                <div className="mt-1">
                  <Badge variant={healthResult.data?.status === 'ok' ? 'success' : 'warning'}>
                    {healthResult.data?.status}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-gray-500">Uptime</p>
                <p className="mt-1 text-lg font-semibold text-white">
                  {formatUptime(healthResult.data?.uptime_seconds ?? 0)}
                </p>
              </div>
            </div>
          </div>
        )}
      </Section>

      {/* Plugins */}
      <Section
        title="Plugins"
        description="Registered extensions and integrations"
        action={
          <button
            onClick={pluginsResult.refetch}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-white transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
        }
      >
        {pluginsResult.status === 'loading' ? (
          <Spinner />
        ) : pluginsResult.status === 'error' ? (
          <ErrorDisplay error={pluginsResult.error} onRetry={pluginsResult.refetch} />
        ) : pluginsResult.data?.length === 0 ? (
          <EmptyState message="No plugins registered" icon={<Puzzle className="h-10 w-10" />} />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {pluginsResult.data?.map((plugin) => (
              <div
                key={plugin.name}
                className="rounded-lg border border-gray-800 bg-gray-900/40 p-4 hover:border-gray-700 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Puzzle className="h-4 w-4 text-memoria-400" />
                    <span className="font-medium text-white">{plugin.name}</span>
                  </div>
                  <Badge variant={plugin.enabled ? 'success' : 'default'}>
                    {plugin.enabled ? 'Active' : 'Disabled'}
                  </Badge>
                </div>
                {plugin.description && (
                  <p className="mt-2 text-xs text-gray-400">{plugin.description}</p>
                )}
                <p className="mt-1 text-[10px] text-gray-600">v{plugin.version}</p>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* Streams */}
      <Section
        title="Event Streams"
        description="Active data pipelines and consumers"
        action={
          <button
            onClick={streamsResult.refetch}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-white transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Refresh
          </button>
        }
      >
        {streamsResult.status === 'loading' ? (
          <Spinner />
        ) : streamsResult.status === 'error' ? (
          <ErrorDisplay error={streamsResult.error} onRetry={streamsResult.refetch} />
        ) : !streamsResult.data || Object.keys(streamsResult.data).length === 0 ? (
          <EmptyState message="No active streams" icon={<Radio className="h-10 w-10" />} />
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-800">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60">
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Stream
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Length
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Consumers
                  </th>
                  <th className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-gray-500">
                    Last Entry
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(streamsResult.data).map(([name, info]) => (
                  <tr
                    key={name}
                    className="border-b border-gray-800/50 hover:bg-gray-900/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-white">{name}</td>
                    <td className="px-4 py-3 text-gray-300">{info.length}</td>
                    <td className="px-4 py-3 text-gray-300">{info.consumers}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {info.last_entry_id || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}
