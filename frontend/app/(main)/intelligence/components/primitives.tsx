'use client';

import { Badge, Button, Card, Flex, Heading, Select, Text, TextField } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { ErrorType, isProcessedError } from '@/lib/api';
import type { PageMeta } from '../types';

export function isNotFoundError(error: unknown): boolean {
  return isProcessedError(error) && (error.type === ErrorType.NOT_FOUND || error.statusCode === 404);
}

function errorMessage(error: unknown): string {
  if (isProcessedError(error)) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong while loading intelligence data.';
}

export function PortalHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <Flex justify="between" align="start" gap="4" wrap="wrap">
      <Flex direction="column" gap="1">
        <Heading size="6" style={{ color: 'var(--slate-12)' }}>
          {title}
        </Heading>
        {subtitle ? (
          <Text size="2" style={{ color: 'var(--slate-11)' }}>
            {subtitle}
          </Text>
        ) : null}
      </Flex>
      {actions}
    </Flex>
  );
}

export function KpiCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: string;
  hint?: string;
  icon: string;
}) {
  return (
    <Card size="2" style={{ flex: '1 1 180px', minWidth: 180 }}>
      <Flex direction="column" gap="2">
        <Flex align="center" gap="2">
          <MaterialIcon name={icon} size={18} color="var(--accent-9)" />
          <Text size="1" weight="medium" style={{ color: 'var(--slate-11)' }}>
            {label}
          </Text>
        </Flex>
        <Heading size="6" style={{ color: 'var(--slate-12)' }}>
          {value}
        </Heading>
        {hint ? (
          <Text size="1" style={{ color: 'var(--slate-10)' }}>
            {hint}
          </Text>
        ) : null}
      </Flex>
    </Card>
  );
}

export function EmptyState({ icon, title, description }: { icon: string; title: string; description?: string }) {
  return (
    <Flex direction="column" align="center" justify="center" gap="2" style={{ padding: 'var(--space-8) 0' }}>
      <MaterialIcon name={icon} size={40} color="var(--slate-8)" />
      <Text size="3" weight="medium" style={{ color: 'var(--slate-12)' }}>
        {title}
      </Text>
      {description ? (
        <Text size="2" style={{ color: 'var(--slate-11)', textAlign: 'center', maxWidth: 420 }}>
          {description}
        </Text>
      ) : null}
    </Flex>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = errorMessage(error);
  return (
    <Flex direction="column" align="center" justify="center" gap="3" style={{ padding: 'var(--space-8) 0' }}>
      <MaterialIcon name="error" size={40} color="var(--red-9)" />
      <Text size="2" style={{ color: 'var(--red-11)', textAlign: 'center' }}>
        {message}
      </Text>
      {onRetry ? (
        <Button variant="soft" color="gray" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </Flex>
  );
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <Flex direction="column" gap="2" style={{ padding: 'var(--space-3) 0' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 36,
            borderRadius: 'var(--radius-2)',
            backgroundColor: 'var(--slate-3)',
            opacity: 1 - i * 0.12,
          }}
        />
      ))}
    </Flex>
  );
}

export function ConnectorBadges({ connectors }: { connectors: string[] }) {
  if (connectors.length === 0) return <Text size="1" style={{ color: 'var(--slate-10)' }}>—</Text>;
  return (
    <Flex gap="1" wrap="wrap">
      {connectors.map((c) => (
        <Badge key={c} color="gray" variant="soft" size="1">
          {c}
        </Badge>
      ))}
    </Flex>
  );
}

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
    <Flex gap="3" wrap="wrap" align="center">
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
    <Flex justify="between" align="center" gap="3" wrap="wrap">
      <Text size="1" style={{ color: 'var(--slate-11)' }}>
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
