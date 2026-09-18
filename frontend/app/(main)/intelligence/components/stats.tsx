'use client';

import { Box, Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export type StatItem = {
  label: string;
  value: string;
  hint?: string;
  icon?: string;
};

export function StatStrip({ items }: { items: StatItem[] }) {
  return (
    <Flex gap="3" wrap="wrap" mb="5">
      {items.map((item) => (
        <Box
          key={item.label}
          style={{
            ...portal.panel,
            flex: '1 1 180px',
            minWidth: 160,
            padding: '18px 20px',
          }}
        >
          <Flex direction="column" gap="2">
            <Flex align="center" gap="2">
              {item.icon ? <MaterialIcon name={item.icon} size={16} color="var(--emerald-10)" /> : null}
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
              <Text size="1" style={{ color: 'var(--slate-10)' }}>
                {item.hint}
              </Text>
            ) : null}
          </Flex>
        </Box>
      ))}
    </Flex>
  );
}
