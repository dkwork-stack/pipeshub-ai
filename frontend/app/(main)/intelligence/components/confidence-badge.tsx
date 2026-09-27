'use client';

import { Badge, Tooltip } from '@radix-ui/themes';
import { formatConfidence } from './format';

/** Mentions below this are still shown but highlighted as lower confidence. */
export const CONFIDENCE_THRESHOLD = 0.5;

export function ConfidenceBadge({
  value,
  threshold = CONFIDENCE_THRESHOLD,
}: {
  value: number | null | undefined;
  threshold?: number;
}) {
  if (value === null || value === undefined) {
    return (
      <Badge color="gray" variant="soft" size="1">
        —
      </Badge>
    );
  }
  const low = value < threshold;
  return (
    <Tooltip content={low ? `Below ${Math.round(threshold * 100)}% threshold` : 'Model confidence'}>
      <Badge color={low ? 'amber' : 'teal'} variant="soft" size="1">
        {formatConfidence(value)}
      </Badge>
    </Tooltip>
  );
}
