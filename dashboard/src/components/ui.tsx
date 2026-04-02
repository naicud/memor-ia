import { clsx } from 'clsx';
import type { ReactNode } from 'react';

interface CardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
}

export function StatCard({ title, value, subtitle, icon, className }: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-gray-800 bg-gray-900/60 p-5 backdrop-blur-sm',
        'hover:border-memoria-700/50 transition-colors duration-200',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-400">{title}</p>
          <p className="mt-1 text-3xl font-bold tracking-tight text-white">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
          {subtitle && <p className="mt-1 text-xs text-gray-500">{subtitle}</p>}
        </div>
        {icon && (
          <div className="rounded-lg bg-memoria-900/30 p-2 text-memoria-400">{icon}</div>
        )}
      </div>
    </div>
  );
}

interface SectionProps {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}

export function Section({ title, description, children, action }: SectionProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          {description && <p className="text-sm text-gray-400">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
}

const badgeColors = {
  default: 'bg-gray-800 text-gray-300',
  success: 'bg-emerald-900/50 text-emerald-400 border-emerald-800',
  warning: 'bg-amber-900/50 text-amber-400 border-amber-800',
  error: 'bg-red-900/50 text-red-400 border-red-800',
  info: 'bg-memoria-900/50 text-memoria-400 border-memoria-800',
};

export function Badge({ children, variant = 'default' }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium',
        badgeColors[variant]
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizes = { sm: 'h-4 w-4', md: 'h-6 w-6', lg: 'h-10 w-10' };
  return (
    <div
      className={clsx(
        'animate-spin rounded-full border-2 border-gray-700 border-t-memoria-500',
        sizes[size]
      )}
    />
  );
}

export function EmptyState({ message, icon }: { message: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-500">
      {icon && <div className="mb-3 text-gray-600">{icon}</div>}
      <p className="text-sm">{message}</p>
    </div>
  );
}

export function ErrorDisplay({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-900/50 bg-red-950/30 p-6 text-center">
      <p className="text-sm text-red-400">{error.message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg bg-red-900/50 px-4 py-1.5 text-xs font-medium text-red-300 hover:bg-red-900/70 transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
