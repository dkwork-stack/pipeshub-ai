'use client';

import { Flex, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';
import type { SortDirection } from './use-client-sort';

export function SortableHeader<K extends string>({
  label,
  sortKey,
  activeKey,
  dir,
  onSort,
  align,
}: {
  label: string;
  sortKey: K;
  activeKey: K;
  dir: SortDirection;
  onSort: (key: K) => void;
  align?: 'left' | 'right' | 'center';
}) {
  const active = sortKey === activeKey;
  return (
    <Table.ColumnHeaderCell
      align={align}
      onClick={() => onSort(sortKey)}
      style={{ cursor: 'pointer', userSelect: 'none' }}
    >
      <Flex align="center" justify={align === 'right' ? 'end' : 'start'} gap="1">
        <Text size="1" weight={active ? 'bold' : 'medium'} style={{ color: active ? portal.strong : portal.muted }}>
          {label}
        </Text>
        <MaterialIcon
          name={active ? (dir === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'unfold_more'}
          size={14}
          color={active ? portal.colors.blue : portal.muted}
        />
      </Flex>
    </Table.ColumnHeaderCell>
  );
}
