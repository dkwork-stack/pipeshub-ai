'use client';

import { Flex } from '@radix-ui/themes';
import { portal } from './theme';

/** Simple deterministic string hash — same name always gets the same color. */
function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return hash;
}

/**
 * Initials avatar. Purely decorative (color/initial derived from the real
 * name) — not a stand-in for data we don't have.
 */
export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const trimmed = name.trim();
  const initial = trimmed ? trimmed[0].toUpperCase() : '?';
  const color = portal.avatarPalette[hashString(trimmed) % portal.avatarPalette.length];

  return (
    <Flex
      align="center"
      justify="center"
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: color,
        color: '#ffffff',
        fontSize: Math.round(size * 0.42),
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {initial}
    </Flex>
  );
}
