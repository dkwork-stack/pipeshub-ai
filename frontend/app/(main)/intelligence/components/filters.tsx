'use client';

import { Button, Flex, Select, Text, TextField } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { PageMeta } from '../types';
import { portal } from './theme';

const ALL_CONNECTORS = '__all__';

export function FiltersBar({
  query,
  onQueryChange,
  minArr,
  onMinArrChange,
  connector,
  onConnectorChange,
  connectors,
  searchPlaceholder,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  minArr: string;
  onMinArrChange: (v: string) => void;
  connector: string;
  onConnectorChange: (v: string) => void;
  connectors: string[];
  searchPlaceholder: string;
}) {
  return (
    <Flex
      gap="3"
      wrap="wrap"
      align="center"
      p="3"
      mb="4"
      style={{
        ...portal.panel,
        borderRadius: 14,
      }}
    >
      <TextField.Root
        size="2"
        placeholder={searchPlaceholder}
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        style={{ minWidth: 260, flex: '1 1 260px' }}
      >
        <TextField.Slot>
          <MaterialIcon name="search" size={16} color="var(--slate-9)" />
        </TextField.Slot>
      </TextField.Root>
      <TextField.Root
        size="2"
        type="number"
        min={0}
        placeholder="Min ARR (USD)"
        value={minArr}
        onChange={(e) => onMinArrChange(e.target.value)}
        style={{ width: 160 }}
      >
        <TextField.Slot>
          <MaterialIcon name="attach_money" size={16} color="var(--slate-9)" />
        </TextField.Slot>
      </TextField.Root>
      <Select.Root
        size="2"
        value={connector || ALL_CONNECTORS}
        onValueChange={(v) => onConnectorChange(v === ALL_CONNECTORS ? '' : v)}
      >
        <Select.Trigger placeholder="Source" style={{ minWidth: 160 }} />
        <Select.Content>
          <Select.Item value={ALL_CONNECTORS}>All sources</Select.Item>
          {connectors.map((c) => (
            <Select.Item key={c} value={c}>
              {c}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
    </Flex>
  );
}

export function PaginationBar({
  page,
  onOffsetChange,
}: {
  page: PageMeta | undefined;
  onOffsetChange: (offset: number) => void;
}) {
  if (!page) return null;
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.limit, page.total);
  return (
    <Flex justify="between" align="center" gap="3" wrap="wrap" mt="3">
      <Text size="1" style={{ color: portal.muted }}>
        Showing {start}–{end} of {page.total}
      </Text>
      <Flex gap="2">
        <Button
          size="1"
          variant="soft"
          color="gray"
          disabled={page.offset === 0}
          onClick={() => onOffsetChange(Math.max(0, page.offset - page.limit))}
        >
          Previous
        </Button>
        <Button
          size="1"
          variant="soft"
          color="gray"
          disabled={!page.has_more}
          onClick={() => onOffsetChange(page.offset + page.limit)}
        >
          Next
        </Button>
      </Flex>
    </Flex>
  );
}
