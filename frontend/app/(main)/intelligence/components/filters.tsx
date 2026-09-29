'use client';

import { Flex, IconButton, Select, Text, TextField } from '@radix-ui/themes';
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
  hideMinArr = false,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  minArr: string;
  onMinArrChange: (v: string) => void;
  connector: string;
  onConnectorChange: (v: string) => void;
  connectors: string[];
  searchPlaceholder: string;
  hideMinArr?: boolean;
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
        style={{ minWidth: 260, flex: '1 1 260px', ...portal.input }}
      >
        <TextField.Slot>
          <MaterialIcon name="search" size={16} color={portal.muted} />
        </TextField.Slot>
      </TextField.Root>
      {!hideMinArr ? (
        <TextField.Root
          size="2"
          type="number"
          min={0}
          placeholder="Min ARR (USD)"
          value={minArr}
          onChange={(e) => onMinArrChange(e.target.value)}
          style={{ width: 160, ...portal.input }}
        >
          <TextField.Slot>
            <MaterialIcon name="attach_money" size={16} color={portal.muted} />
          </TextField.Slot>
        </TextField.Root>
      ) : null}
      <Select.Root
        size="2"
        value={connector || ALL_CONNECTORS}
        onValueChange={(v) => onConnectorChange(v === ALL_CONNECTORS ? '' : v)}
      >
        <Select.Trigger placeholder="Source" style={{ minWidth: 160, ...portal.input }} />
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

/** Compact "1–20 of 156" + circular chevron controls, meant to sit in a panel's header action slot. */
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
    <Flex align="center" gap="2">
      <Text size="1" style={{ color: portal.muted, whiteSpace: 'nowrap' }}>
        {start}–{end} of {page.total}
      </Text>
      <IconButton
        size="1"
        variant="soft"
        radius="full"
        aria-label="Previous page"
        disabled={page.offset === 0}
        onClick={() => onOffsetChange(Math.max(0, page.offset - page.limit))}
        style={{ ...portal.input, opacity: page.offset === 0 ? 0.5 : 1 }}
      >
        <MaterialIcon name="chevron_left" size={16} color={portal.strong} />
      </IconButton>
      <IconButton
        size="1"
        variant="soft"
        radius="full"
        aria-label="Next page"
        disabled={!page.has_more}
        onClick={() => onOffsetChange(page.offset + page.limit)}
        style={{ ...portal.input, opacity: !page.has_more ? 0.5 : 1 }}
      >
        <MaterialIcon name="chevron_right" size={16} color={portal.strong} />
      </IconButton>
    </Flex>
  );
}
