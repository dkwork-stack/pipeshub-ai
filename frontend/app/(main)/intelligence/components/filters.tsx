'use client';

import { Box, Flex, IconButton, Select, Text, TextField, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { PageMeta } from '../types';
import { formatConnectorLabel } from './connector-display';
import { portal } from './theme';

const ALL_CONNECTORS = '__all__';

/** Search + source filter only — no outer card chrome. */
export function FiltersBar({
  query,
  onQueryChange,
  connector,
  onConnectorChange,
  connectors,
  searchPlaceholder,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  connector: string;
  onConnectorChange: (v: string) => void;
  connectors: string[];
  searchPlaceholder: string;
}) {
  return (
    <Flex gap="3" wrap="wrap" align="center" mb="4">
      <Tooltip content={searchPlaceholder}>
        <Box style={{ minWidth: 260, flex: '1 1 260px' }}>
          <TextField.Root
            size="2"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            aria-label={searchPlaceholder}
            style={{ width: '100%', ...portal.input }}
          >
            <TextField.Slot>
              <MaterialIcon name="search" size={16} color={portal.muted} />
            </TextField.Slot>
          </TextField.Root>
        </Box>
      </Tooltip>
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
              {formatConnectorLabel(c)}
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
