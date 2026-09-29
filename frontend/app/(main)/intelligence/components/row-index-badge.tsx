'use client';

import { Flex } from '@radix-ui/themes';
import { portal } from './theme';

export function RowIndexBadge({ index }: { index: number }) {
  return (
    <Flex
      align="center"
      justify="center"
      style={{
        width: 24,
        height: 24,
        borderRadius: '50%',
        backgroundColor: portal.colors.blueSoftBg,
        color: portal.colors.blue,
        fontSize: 12,
        fontWeight: 700,
        flexShrink: 0,
      }}
    >
      {index}
    </Flex>
  );
}
