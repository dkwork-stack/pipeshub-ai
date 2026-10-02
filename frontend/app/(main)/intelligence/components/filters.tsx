'use client';

import type { ReactNode } from 'react';
import { Box, Flex, IconButton, Select, Text, TextField, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { PageMeta } from '../types';
import { formatConnectorLabel } from './connector-display';
import { portal } from './theme';

const ALL_CONNECTORS = '__all__';
const ALL_CONF = '__all__';

export const CONFIDENCE_FILTER_OPTIONS = [
  { value: ALL_CONF, label: 'All confidence' },
  { value: '0.5', label: '≥ 50%' },
  { value: '0.7', label: '≥ 70%' },
  { value: '0.9', label: '≥ 90%' },
] as const;

const filterControlStyle = {
  ...portal.input,
  height: portal.control.height,
  minHeight: portal.control.height,
  display: 'inline-flex',
  alignItems: 'center',
} as const;

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
    <Flex gap="3" wrap="wrap" align="center" mb="4" className="intelligence-filters">
      <Tooltip content={searchPlaceholder}>
        <Box style={{ minWidth: 300, flex: '1 1 300px' }}>
          <TextField.Root
            size="3"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            aria-label={searchPlaceholder}
            style={{ width: '100%', ...filterControlStyle }}
          >
            <TextField.Slot>
              <MaterialIcon name="search" size={18} color={portal.muted} />
            </TextField.Slot>
          </TextField.Root>
        </Box>
      </Tooltip>
      <Select.Root
        size="3"
        value={connector || ALL_CONNECTORS}
        onValueChange={(v) => onConnectorChange(v === ALL_CONNECTORS ? '' : v)}
      >
        <Select.Trigger placeholder="Source" style={{ width: 200, ...filterControlStyle }} />
        <Select.Content className="intelligence-select-content" position="popper">
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

/** Source + confidence selects for Evidence panels — same size as FiltersBar. */
export function EvidenceFilters({
  connector,
  onConnectorChange,
  connectors,
  minConfidence,
  onMinConfidenceChange,
  extra,
}: {
  connector: string;
  onConnectorChange: (v: string) => void;
  connectors: string[];
  minConfidence: string;
  onMinConfidenceChange: (v: string) => void;
  extra?: ReactNode;
}) {
  return (
    <Flex gap="2" align="center" wrap="wrap" className="intelligence-filters">
      {extra}
      <Select.Root
        size="3"
        value={connector || ALL_CONNECTORS}
        onValueChange={(v) => onConnectorChange(v === ALL_CONNECTORS ? '' : v)}
      >
        <Select.Trigger placeholder="Source" style={{ width: 200, ...filterControlStyle }} />
        <Select.Content className="intelligence-select-content" position="popper">
          <Select.Item value={ALL_CONNECTORS}>All sources</Select.Item>
          {connectors.map((c) => (
            <Select.Item key={c} value={c}>
              {formatConnectorLabel(c)}
            </Select.Item>
          ))}
        </Select.Content>
      </Select.Root>
      <Select.Root
        size="3"
        value={minConfidence || ALL_CONF}
        onValueChange={(v) => onMinConfidenceChange(v === ALL_CONF ? '' : v)}
      >
        <Select.Trigger style={{ width: 200, ...filterControlStyle }} />
        <Select.Content className="intelligence-select-content" position="popper">
          {CONFIDENCE_FILTER_OPTIONS.map((o) => (
            <Select.Item key={o.value} value={o.value}>
              {o.label}
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
        style={{ ...portal.input, height: 28, minHeight: 28, opacity: page.offset === 0 ? 0.5 : 1 }}
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
        style={{ ...portal.input, height: 28, minHeight: 28, opacity: !page.has_more ? 0.5 : 1 }}
      >
        <MaterialIcon name="chevron_right" size={16} color={portal.strong} />
      </IconButton>
    </Flex>
  );
}
