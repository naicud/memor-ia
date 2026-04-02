import { api } from '@/lib/api';
import { usePolling } from '@/hooks/useAsync';
import { StatCard, Section, Spinner, ErrorDisplay, Badge } from '@/components/ui';
import {
  Database,
  Layers,
  Paperclip,
  Puzzle,
  Activity,
  Clock,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';

const COLORS = ['#5c7cfa', '#748ffc', '#91a7ff', '#bac8ff', '#dbe4ff'];

export function OverviewPage() {
  const health = usePolling(() => api.health(), 10000);
  const stats = usePolling(() => api.stats(), 10000);
  const namespaces = usePolling(() => api.namespaces(), 15000);

  if (health.status === 'loading' && stats.status === 'loading') {
    return (
      <div className="flex items-center justify-center h-96">
        <Spinner size="lg" />
      </div>
    );
  }

  if (health.status === 'error') {
    return <ErrorDisplay error={health.error} onRetry={health.refetch} />;
  }

  const statsData = stats.data;
  const healthData = health.data;
  const nsData = namespaces.data ?? [];

  const barData = nsData.map((ns) => ({
    name: ns.name.length > 12 ? ns.name.slice(0, 12) + '…' : ns.name,
    memories: ns.count,
  }));

  const pieData = nsData.map((ns) => ({
    name: ns.name,
    value: ns.count,
  }));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Overview</h1>
          <p className="text-sm text-gray-400">Real-time system monitoring</p>
        </div>
        <div className="flex items-center gap-3">
          {healthData && (
            <>
              <Badge variant={healthData.status === 'ok' ? 'success' : 'warning'}>
                <Activity className="mr-1 h-3 w-3" />
                {healthData.status}
              </Badge>
              <Badge variant="info">v{healthData.version}</Badge>
            </>
          )}
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Memories"
          value={statsData?.total_memories ?? '—'}
          icon={<Database className="h-5 w-5" />}
          subtitle="Across all namespaces"
        />
        <StatCard
          title="Namespaces"
          value={statsData?.namespace_count ?? '—'}
          icon={<Layers className="h-5 w-5" />}
          subtitle="Active memory spaces"
        />
        <StatCard
          title="Attachments"
          value={statsData?.attachments ?? '—'}
          icon={<Paperclip className="h-5 w-5" />}
          subtitle="Linked files & media"
        />
        <StatCard
          title="Plugins"
          value={statsData?.plugin_count ?? '—'}
          icon={<Puzzle className="h-5 w-5" />}
          subtitle="Registered extensions"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Bar Chart */}
        <Section title="Memories by Namespace" description="Distribution across memory spaces">
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={barData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis
                    dataKey="name"
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                  />
                  <YAxis
                    tick={{ fill: '#6b7280', fontSize: 11 }}
                    axisLine={{ stroke: '#374151' }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#e5e7eb',
                    }}
                  />
                  <Bar dataKey="memories" fill="#5c7cfa" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[280px] text-gray-600 text-sm">
                No namespace data
              </div>
            )}
          </div>
        </Section>

        {/* Pie Chart */}
        <Section title="Namespace Distribution" description="Relative memory allocation">
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#111827',
                      border: '1px solid #374151',
                      borderRadius: '8px',
                      color: '#e5e7eb',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[280px] text-gray-600 text-sm">
                No data to display
              </div>
            )}
          </div>
        </Section>
      </div>

      {/* System Info */}
      {healthData && (
        <Section title="System Status">
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-5">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="text-xs text-gray-500">Status</p>
                <p className="mt-1 text-sm font-medium text-emerald-400">{healthData.status}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Version</p>
                <p className="mt-1 text-sm font-medium text-white">{healthData.version}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Uptime</p>
                <p className="mt-1 flex items-center gap-1 text-sm font-medium text-white">
                  <Clock className="h-3 w-3 text-gray-500" />
                  {formatUptime(healthData.uptime_seconds)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Namespaces</p>
                <p className="mt-1 text-sm font-medium text-white">{nsData.length}</p>
              </div>
            </div>
          </div>
        </Section>
      )}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
