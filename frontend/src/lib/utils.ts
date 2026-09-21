import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }

export function formatDate(iso: string | null | undefined, opts: { withTime?: boolean; short?: boolean } = {}) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  if (opts.short) return `${mm}-${dd}`;
  const base = `${d.getFullYear()}-${mm}-${dd}`;
  if (!opts.withTime) return base;
  return `${base} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function formatAmount(n: number | null | undefined) {
  if (n === null || n === undefined || Number.isNaN(n)) return '';
  return n.toLocaleString('ko-KR');
}

export function parseAmount(s: string): number | null {
  const digits = s.replace(/[^\d]/g, '');
  return digits ? Number(digits) : null;
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

export function formatBizNo(s: string) {
  const d = s.replace(/\D/g, '').slice(0, 10);
  if (d.length <= 3) return d;
  if (d.length <= 5) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 5)}-${d.slice(5)}`;
}

export function pct(n: number | null | undefined, digits = 0) {
  if (n === null || n === undefined) return '-';
  return `${(n * 100).toFixed(digits)}%`;
}

export function extOf(name: string) { return name.split('.').pop()?.toLowerCase() ?? ''; }
