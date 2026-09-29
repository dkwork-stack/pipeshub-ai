'use client';

import { Box, Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export type StatColor = keyof typeof portal.statPalette;

export type StatItem = {
  label: string;
  value: string;
  hint?: string;
  icon?: string;
  color?: StatColor;
};

/** Decorative bottom wave — visual accent only, not a real trend series. */
function WaveAccent({ color, id }: { color: string; id: string }) {
  const gradId = `wave-fill-${id}`;
  return (
    <Box
      aria-hidden
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        height: 44,
        pointerEvents: 'none',
        overflow: 'hidden',
        borderBottomLeftRadius: 12,
        borderBottomRightRadius: 12,
      }}
    >
      <svg
        viewBox="0 0 240 44"
        preserveAspectRatio="none"
        style={{ width: '100%', height: '100%', display: 'block' }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.22" />
            <stop offset="100%" stopColor={color} stopOpacity="0.04" />
          </linearGradient>
        </defs>
        <path
          d="M0 22 C 30 10, 50 34, 80 22 S 130 8, 160 22 S 210 36, 240 18 L 240 44 L 0 44 Z"
          fill={`url(#${gradId})`}
        />
        <path
          d="M0 22 C 30 10, 50 34, 80 22 S 130 8, 160 22 S 210 36, 240 18"
          fill="none"
          stroke={color}
          strokeWidth="1.75"
          strokeOpacity="0.55"
          strokeLinecap="round"
        />
      </svg>
    </Box>
  );
}

export function StatStrip({ items }: { items: StatItem[] }) {
  return (
    <Flex gap="3" wrap="wrap" mb="5">
      {items.map((item) => {
        const palette = portal.statPalette[item.color ?? 'blue'];
        const waveId = item.label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
        return (
          <Box
            key={item.label}
            style={{
              ...portal.panel,
              flex: '1 1 180px',
              minWidth: 160,
              padding: '18px 20px 28px',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <Flex direction="column" gap="2" style={{ position: 'relative', zIndex: 1 }}>
              <Flex align="center" gap="2">
                {item.icon ? (
                  <Flex
                    align="center"
                    justify="center"
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 9,
                      flexShrink: 0,
                      backgroundColor: palette.bg,
                    }}
                  >
                    <MaterialIcon name={item.icon} size={16} color={palette.fg} />
                  </Flex>
                ) : null}
                <Text size="1" weight="medium" style={{ color: portal.muted }}>
                  {item.label}
                </Text>
              </Flex>
              <Text
                size="7"
                weight="bold"
                style={{
                  color: portal.strong,
                  fontFamily: portal.displayFont,
                  letterSpacing: '-0.03em',
                  lineHeight: 1,
                }}
              >
                {item.value}
              </Text>
              {item.hint ? (
                <Text size="1" style={{ color: portal.muted }}>
                  {item.hint}
                </Text>
              ) : null}
            </Flex>
            <WaveAccent color={palette.fg} id={waveId} />
          </Box>
        );
      })}
    </Flex>
  );
}
