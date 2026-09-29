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

/**
 * Same formula as backend `compute_feature_gap_score` — used when the stored
 * score column is 0/stale so the UI still reflects real ARR × demand.
 */
export function computeFeatureGapScore(
  totalArrAtStake: number,
  customerCount: number,
  mentionCount: number,
): number {
  const revenue = Math.max(totalArrAtStake || 0, 0);
  const breadth = Math.max(customerCount || 0, 0);
  const volumeBoost = 1 + Math.log1p(Math.max(mentionCount || 0, 0));
  return Math.round(revenue * breadth * volumeBoost * 100) / 100;
}

/** Prefer API score when present; otherwise recompute from the row's metrics. */
export function resolveFeatureGapScore(gap: {
  score: number;
  total_arr_at_stake: number;
  customer_count: number;
  mention_count: number;
}): number {
  if (typeof gap.score === 'number' && gap.score > 0) return gap.score;
  return computeFeatureGapScore(gap.total_arr_at_stake, gap.customer_count, gap.mention_count);
}

/**
 * Normalize a raw priority score into 0–1 relative to the strongest row on
 * the current page — matches the mock's 0.92 / 0.85 style without inventing data.
 */
export function relativeScore(raw: number, maxRaw: number): number {
  if (maxRaw <= 0) return 0;
  return Math.min(1, Math.max(0, raw / maxRaw));
}
