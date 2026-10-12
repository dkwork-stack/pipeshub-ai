'use client';

import { Badge, Box, Flex, Text } from '@radix-ui/themes';
import type { TopicTrend } from '../types';
import { formatCount, formatDate } from './format';
import { portal } from './theme';
import { MixBar, TrendIndicator, toneSegments, urgencySegments } from './trend';

/**
 * How customers talk about one topic: recency, urgency and tone mix,
 * competitors named and churn signals — all aggregated from its evidence.
 */
export function TopicSignals({ trend }: { trend: TopicTrend | null | undefined }) {
  if (!trend) {
    return (
      <Text size="2" style={{ color: portal.muted }}>
        Signals appear after the next sync analyses this topic&apos;s evidence.
      </Text>
    );
  }
  return (
    <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 24 }}>
      <Flex direction="column" gap="2">
        <Label>Activity</Label>
        <Flex justify="between" align="center">
          <Text size="2" style={{ color: portal.muted }}>
            Last 30 days
          </Text>
          <TrendIndicator trend={trend} />
        </Flex>
        <Flex justify="between">
          <Text size="2" style={{ color: portal.muted }}>
            First seen
          </Text>
          <Text size="2">{formatDate(trend.first_seen_at)}</Text>
        </Flex>
        <Flex justify="between">
          <Text size="2" style={{ color: portal.muted }}>
            Last seen
          </Text>
          <Text size="2">{formatDate(trend.last_seen_at)}</Text>
        </Flex>
      </Flex>
      <Flex direction="column" gap="2">
        <Label>Urgency</Label>
        <MixBar segments={urgencySegments(trend.urgencies)} />
        <Label>Tone</Label>
        <MixBar segments={toneSegments(trend.tones)} />
      </Flex>
      <Flex direction="column" gap="2">
        <Label>Risk</Label>
        <Flex justify="between">
          <Text size="2" style={{ color: portal.muted }}>
            Churn signals
          </Text>
          <Text size="2" weight="medium" style={{ color: trend.churn_risk_count ? portal.signal.negative.fg : portal.strong }}>
            {formatCount(trend.churn_risk_count)}
          </Text>
        </Flex>
        <Flex justify="between">
          <Text size="2" style={{ color: portal.muted }}>
            Negative sentiment
          </Text>
          <Text size="2" weight="medium">
            {Math.round(trend.negative_share * 100)}%
          </Text>
        </Flex>
        <Text size="2" style={{ color: portal.muted }}>
          Competitors named
        </Text>
        {trend.competitors.length === 0 ? (
          <Text size="2">—</Text>
        ) : (
          <Flex gap="1" wrap="wrap">
            {trend.competitors.map((c) => (
              <Badge key={c} variant="soft" size="1" style={{ backgroundColor: portal.signal.attention.bg, color: portal.signal.attention.fg }}>
                {c}
              </Badge>
            ))}
          </Flex>
        )}
      </Flex>
    </Box>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <Text size="1" weight="bold" style={{ color: portal.strong, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
      {children}
    </Text>
  );
}
