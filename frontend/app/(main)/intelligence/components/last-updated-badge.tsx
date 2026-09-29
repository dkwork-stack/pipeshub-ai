'use client';

import { Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { formatDate } from './format';
import { portal } from './theme';

/** Highlighted "last evidence" indicator — real date only, no fake "as of" filter. */
export function LastUpdatedBadge({ date }: { date: string | null | undefined }) {
  if (!date) return null;
  return (
    <Flex
      align="center"
      gap="2"
      style={{
        backgroundColor: portal.colors.blueSoftBg,
        border: `1px solid ${portal.colors.border}`,
        borderRadius: 999,
        padding: '8px 14px 8px 8px',
      }}
    >
      <Flex
        align="center"
        justify="center"
        style={{ width: 28, height: 28, borderRadius: '50%', backgroundColor: '#ffffff', flexShrink: 0 }}
      >
        <MaterialIcon name="event_available" size={15} color={portal.colors.blue} />
      </Flex>
      <Flex direction="column" gap="0">
        <Text size="1" style={{ color: portal.muted, lineHeight: 1.2 }}>
          Last updated
        </Text>
        <Text size="2" weight="bold" style={{ color: portal.colors.blue, lineHeight: 1.2 }}>
          {formatDate(date)}
        </Text>
      </Flex>
    </Flex>
  );
}
