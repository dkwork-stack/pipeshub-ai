'use client';

import { Badge } from '@radix-ui/themes';
import { portal } from './theme';

/** Green above the threshold, amber below — shared by Score and Confidence columns. */
export function ScoreBadge({
  label,
  value,
  threshold,
}: {
  label: string;
  value: number;
  threshold: number;
}) {
  const good = value >= threshold;
  const palette = good ? portal.semantic.good : portal.semantic.warn;
  return (
    <Badge variant="soft" size="1" style={{ backgroundColor: palette.bg, color: palette.fg }}>
      {label}
    </Badge>
  );
}
