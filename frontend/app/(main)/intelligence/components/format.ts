const currency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

const compactCurrency = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
});

export function formatMoney(value: number | null | undefined, compact = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return compact ? compactCurrency.format(value) : currency.format(value);
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-US').format(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${Math.round(value * 100)}%`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}
