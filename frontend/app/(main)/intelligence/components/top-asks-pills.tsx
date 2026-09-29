'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Badge, Box, Flex, Text } from '@radix-ui/themes';
import type { CustomerInsight } from '../types';
import { portal } from './theme';

const VISIBLE_COUNT = 2;

/**
 * Top-asks pills: at most 2 visible; "+N more" expands the rest in-place.
 * Each pill links to the feature-gap detail page.
 */
export function TopAsksPills({ insights }: { insights: CustomerInsight[] }) {
  const [expanded, setExpanded] = useState(false);

  if (insights.length === 0) {
    return (
      <Text size="1" style={{ color: portal.muted }}>
        —
      </Text>
    );
  }

  const visible = expanded ? insights : insights.slice(0, VISIBLE_COUNT);
  const hiddenCount = insights.length - VISIBLE_COUNT;

  return (
    <Box style={{ maxWidth: 280 }}>
      <Flex gap="1" wrap="wrap" align="center">
        {visible.map((insight) => (
          <Link
            key={insight.feature_name}
            href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(insight.feature_name)}`}
            style={{ textDecoration: 'none' }}
          >
            <Badge
              variant="soft"
              size="1"
              style={{
                backgroundColor: portal.colors.blueSoftBg,
                color: portal.colors.blue,
                borderRadius: 999,
                maxWidth: 130,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {insight.feature_name} · {insight.mention_count}
            </Badge>
          </Link>
        ))}
        {!expanded && hiddenCount > 0 ? (
          <Badge
            variant="soft"
            size="1"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setExpanded(true);
            }}
            style={{
              backgroundColor: portal.colors.tableHeaderBg,
              color: portal.muted,
              borderRadius: 999,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            +{hiddenCount} more
          </Badge>
        ) : null}
        {expanded && insights.length > VISIBLE_COUNT ? (
          <Badge
            variant="soft"
            size="1"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setExpanded(false);
            }}
            style={{
              backgroundColor: portal.colors.tableHeaderBg,
              color: portal.muted,
              borderRadius: 999,
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            Show less
          </Badge>
        ) : null}
      </Flex>
    </Box>
  );
}
