'use client';

import { Box, Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { TopicTrend } from '../types';
import { formatCount } from './format';
import { portal } from './theme';

/**
 * Mentions in the last 30 days with the change against the 30 before —
 * computed server-side from evidence dates, never interpolated.
 */
export function TrendIndicator({ trend }: { trend: TopicTrend | null | undefined }) {
  if (!trend) {
    return (
      <Text size="1" style={{ color: portal.muted }}>
        —
      </Text>
    );
  }
  const delta = trend.mentions_last_30d - trend.mentions_prev_30d;
  const isNew = trend.mentions_prev_30d === 0 && trend.mentions_last_30d > 0;
  const palette = delta > 0 ? portal.signal.attention : delta < 0 ? portal.signal.positive : portal.signal.neutral;
  const icon = delta > 0 ? 'trending_up' : delta < 0 ? 'trending_down' : 'trending_flat';
  const label = isNew ? 'New' : delta === 0 ? '±0' : `${delta > 0 ? '+' : ''}${delta}`;
  return (
    <Tooltip
      content={`${formatCount(trend.mentions_last_30d)} mentions in the last 30 days, ${formatCount(trend.mentions_prev_30d)} in the 30 before`}
    >
      <Flex align="center" gap="1" justify="end">
        <Text size="2" style={{ color: portal.strong }}>
          {formatCount(trend.mentions_last_30d)}
        </Text>
        <Flex
          align="center"
          gap="1"
          style={{ backgroundColor: palette.bg, color: palette.fg, borderRadius: 999, padding: '1px 6px' }}
        >
          <MaterialIcon name={icon} size={12} color={palette.fg} />
          <Text size="1" weight="medium">
            {label}
          </Text>
        </Flex>
      </Flex>
    </Tooltip>
  );
}

export type MixSegment = { key: string; label: string; value: number; color: string };

/** Stacked share bar with a legend; widths are exact proportions of real counts. */
export function MixBar({ segments, height = 8, legend = true }: { segments: MixSegment[]; height?: number; legend?: boolean }) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total === 0) {
    return (
      <Text size="1" style={{ color: portal.muted }}>
        No data yet
      </Text>
    );
  }
  const visible = segments.filter((s) => s.value > 0);
  return (
    <Flex direction="column" gap="2" style={{ width: '100%' }}>
      <Flex style={{ width: '100%', height, borderRadius: height / 2, overflow: 'hidden', backgroundColor: portal.colors.border }}>
        {visible.map((s) => (
          <Tooltip key={s.key} content={`${s.label}: ${formatCount(s.value)} (${Math.round((s.value / total) * 100)}%)`}>
            <Box style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color, height: '100%' }} />
          </Tooltip>
        ))}
      </Flex>
      {legend ? (
        <Flex gap="3" wrap="wrap">
          {visible.map((s) => (
            <Flex key={s.key} align="center" gap="1">
              <Box style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: s.color }} />
              <Text size="1" style={{ color: portal.muted }}>
                {s.label} <Text style={{ color: portal.strong }}>{Math.round((s.value / total) * 100)}%</Text>
              </Text>
            </Flex>
          ))}
        </Flex>
      ) : null}
    </Flex>
  );
}

const SENTIMENT_COLORS: Record<string, string> = {
  Negative: portal.signal.negative.fg,
  Neutral: '#94a3b8',
  Positive: portal.signal.positive.fg,
};

const URGENCY_ORDER: [string, string, string][] = [
  ['critical', 'Critical', portal.signal.negative.fg],
  ['high', 'High', '#f59e0b'],
  ['medium', 'Medium', '#94a3b8'],
  ['low', 'Low', '#cbd5e1'],
];

const TONE_ORDER: [string, string, string][] = [
  ['angry', 'Angry', portal.signal.negative.fg],
  ['frustrated', 'Frustrated', '#f59e0b'],
  ['anxious', 'Anxious', '#facc15'],
  ['neutral', 'Neutral', '#94a3b8'],
  ['appreciative', 'Appreciative', portal.signal.positive.fg],
];

export function sentimentSegments(mix: Record<string, number> | undefined): MixSegment[] {
  return ['Negative', 'Neutral', 'Positive'].map((key) => ({
    key,
    label: key,
    value: mix?.[key] ?? 0,
    color: SENTIMENT_COLORS[key],
  }));
}

export function urgencySegments(mix: Record<string, number> | undefined): MixSegment[] {
  return URGENCY_ORDER.map(([key, label, color]) => ({ key, label, value: mix?.[key] ?? 0, color }));
}

export function toneSegments(mix: Record<string, number> | undefined): MixSegment[] {
  return TONE_ORDER.map(([key, label, color]) => ({ key, label, value: mix?.[key] ?? 0, color }));
}

const INTENT_COLORS = ['#2563eb', '#dc2626', '#9333ea', '#ea580c', '#0891b2', '#16a34a', '#0f172a', '#94a3b8'];

export function intentSegments(mix: Record<string, number> | undefined, labels: Record<string, string>): MixSegment[] {
  return Object.keys(labels).map((key, i) => ({
    key,
    label: labels[key],
    value: mix?.[key] ?? 0,
    color: INTENT_COLORS[i % INTENT_COLORS.length],
  }));
}
