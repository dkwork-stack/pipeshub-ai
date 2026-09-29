'use client';

import { Box } from '@radix-ui/themes';
import { portal } from './theme';

/**
 * Proportional bar (value / max of the currently loaded rows) — a real
 * derived visualization of real numbers, not a fabricated trend.
 */
export function MiniBar({ value, max, color = portal.colors.blue }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <Box style={{ width: '100%', maxWidth: 90, height: 4, borderRadius: 2, backgroundColor: portal.colors.border, marginTop: 4 }}>
      <Box style={{ width: `${pct}%`, height: '100%', borderRadius: 2, backgroundColor: color }} />
    </Box>
  );
}
