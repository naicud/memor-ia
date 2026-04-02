import { NavLink, Outlet } from 'react-router-dom';
import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Database,
  Network,
  ScrollText,
  Settings,
  Brain,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/memories', icon: Database, label: 'Memory Explorer' },
  { to: '/graph', icon: Network, label: 'Knowledge Graph' },
  { to: '/audit', icon: ScrollText, label: 'Audit Log' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-950">
      {/* Sidebar */}
      <aside className="flex w-64 flex-col border-r border-gray-800 bg-gray-950">
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-gray-800 px-5">
          <Brain className="h-7 w-7 text-memoria-500" />
          <div>
            <h1 className="text-base font-bold text-white tracking-tight">Memoria</h1>
            <p className="text-[10px] font-medium text-gray-500 uppercase tracking-widest">
              Dashboard v3.0
            </p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-memoria-900/40 text-memoria-300 border border-memoria-800/50'
                    : 'text-gray-400 hover:bg-gray-900 hover:text-gray-200 border border-transparent'
                )
              }
            >
              <Icon className="h-4.5 w-4.5 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-gray-800 px-5 py-3">
          <p className="text-[10px] text-gray-600">
            Proactive Memory Framework
          </p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
