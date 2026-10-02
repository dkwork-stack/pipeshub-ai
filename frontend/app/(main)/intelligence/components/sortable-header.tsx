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
      style={{ cursor: 'pointer', userSelect: 'none', ...portal.tableHeader, color: portal.colors.tableHeaderText }}
    >
      <Flex align="center" justify={align === 'right' ? 'end' : 'start'} gap="1">
        <Text
          size="1"
          weight="bold"
          style={{ color: active ? portal.colors.blue : portal.colors.tableHeaderText }}
        >
          {label}
        </Text>
        <MaterialIcon
          name={active ? (dir === 'asc' ? 'arrow_upward' : 'arrow_downward') : 'unfold_more'}
          size={14}
          color={active ? portal.colors.blue : portal.colors.tableHeaderText}
        />
      </Flex>
    </Table.ColumnHeaderCell>
  );
}

/** Non-sortable column header with the same high-contrast ink as SortableHeader. */
export function ColumnHeader({
  children,
  align,
  style,
}: {
  children: React.ReactNode;
  align?: 'left' | 'right' | 'center';
  style?: React.CSSProperties;
}) {
  return (
    <Table.ColumnHeaderCell
      align={align}
      style={{ ...portal.tableHeader, color: portal.colors.tableHeaderText, ...style }}
    >
      {children}
    </Table.ColumnHeaderCell>
  );
}
