'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Flex, Table, Text, Tooltip } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import type { PainPoint, TopicStatus } from '../types';
import { usePainPoints, useSourceConnectors } from '../api';
import {
  Avatar,
  ColumnHeader,
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  ExportButton,
  FiltersBar,
  LoadingRows,
  PaginationBar,
  PortalHero,
  RowIndexBadge,
  RowMenu,
  STATUS_OPTIONS,
  SelectFilter,
  SortableHeader,
  StatusBadge,
  SurfacePanel,
  TrendIndicator,
  exportRowsToCsv,
  formatCount,
  portal,
  useClientSort,
} from '../components';

const PAGE_SIZE = 25;

type SortKey = 'topic_name' | 'customer_count' | 'mention_count' | 'max_confidence' | 'recent' | 'negative';

function getSortValue(row: PainPoint, key: SortKey): string | number {
  if (key === 'recent') return row.trend?.mentions_last_30d ?? 0;
  if (key === 'negative') return row.trend?.negative_share ?? 0;
  return row[key];
}

export default function PainPointsPage() {
  const [query, setQuery] = useState('');
  const [connector, setConnector] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);
  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = usePainPoints({
    q: debouncedQuery || undefined,
    source_connector: connector || undefined,
    status: (status || undefined) as TopicStatus | undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const { sorted, sortKey, sortDir, toggleSort } = useClientSort<PainPoint, SortKey>(
    data?.items,
    getSortValue,
    'mention_count',
  );

  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  const handleExport = () => {
    if (!sorted) return;
    exportRowsToCsv(
      'pain-points.csv',
      [
        { header: 'Pain point', accessor: (r: PainPoint) => r.topic_name },
        { header: 'Customers', accessor: (r: PainPoint) => r.customer_count },
        { header: 'Mentions', accessor: (r: PainPoint) => r.mention_count },
        { header: 'Max confidence', accessor: (r: PainPoint) => r.max_confidence },
        { header: 'Status', accessor: (r: PainPoint) => r.status ?? 'open' },
        { header: 'Mentions last 30d', accessor: (r: PainPoint) => r.trend?.mentions_last_30d ?? '' },
        { header: 'Negative share', accessor: (r: PainPoint) => r.trend?.negative_share ?? '' },
        { header: 'Top customers', accessor: (r: PainPoint) => r.top_customers.join('; ') },
      ],
      sorted,
    );
  };

  return (
    <Flex direction="column">
      <PortalHero
        title="Pain points"
        subtitle="Problems customers expressed, grouped across every sync, with how often and how strongly they come up."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search pain point…"
        extra={<SelectFilter value={status} onChange={resetAnd(setStatus)} options={STATUS_OPTIONS} allLabel="Any status" width={170} />}
      />

      <SurfacePanel
        title={`Pain points${data ? ` (${formatCount(data.page.total)})` : ''}`}
        action={
          <Flex align="center" gap="3">
            <ExportButton onExport={handleExport} disabled={!sorted?.length} />
            <PaginationBar page={data?.page} onOffsetChange={setOffset} />
          </Flex>
        }
      >
        {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
        {isLoading && !data ? <LoadingRows rows={8} /> : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            icon="report_problem"
            title="No pain points match"
            description="Try clearing filters, or upload more customer data."
          />
        ) : null}
        {sorted && sorted.length > 0 ? (
          <Table.Root size="2">
            <Table.Header>
              <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                <ColumnHeader>#</ColumnHeader>
                <SortableHeader label="Pain point" sortKey="topic_name" activeKey={sortKey} dir={sortDir} onSort={toggleSort} />
                <SortableHeader label="Customers" sortKey="customer_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Mentions" sortKey="mention_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Confidence" sortKey="max_confidence" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="30-day trend" sortKey="recent" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Negative" sortKey="negative" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <ColumnHeader>Status</ColumnHeader>
                <ColumnHeader>Top customers</ColumnHeader>
                <ColumnHeader>{null}</ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {sorted.map((item, i) => {
                const visibleCustomers = item.top_customers.slice(0, 3);
                const extraCount = item.top_customers.length - visibleCustomers.length;
                return (
                  <Table.Row key={item.topic_name}>
                    <Table.Cell>
                      <RowIndexBadge index={offset + i + 1} />
                    </Table.Cell>
                    <Table.RowHeaderCell>
                      <Link
                        href={`/intelligence/pain-points/detail?name=${encodeURIComponent(item.topic_name)}`}
                        style={{ textDecoration: 'none' }}
                      >
                        <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                          {item.topic_name}
                        </Text>
                      </Link>
                    </Table.RowHeaderCell>
                    <Table.Cell align="right">{formatCount(item.customer_count)}</Table.Cell>
                    <Table.Cell align="right">{formatCount(item.mention_count)}</Table.Cell>
                    <Table.Cell align="right">
                      <ConfidenceBadge value={item.max_confidence} />
                    </Table.Cell>
                    <Table.Cell align="right">
                      <TrendIndicator trend={item.trend} />
                    </Table.Cell>
                    <Table.Cell align="right">
                      <Text size="2" style={{ color: (item.trend?.negative_share ?? 0) >= 0.5 ? portal.signal.negative.fg : portal.strong }}>
                        {item.trend ? `${Math.round(item.trend.negative_share * 100)}%` : '—'}
                      </Text>
                    </Table.Cell>
                    <Table.Cell>
                      <StatusBadge status={item.status} />
                    </Table.Cell>
                    <Table.Cell>
                      {visibleCustomers.length === 0 ? (
                        <Text size="1" style={{ color: portal.muted }}>
                          —
                        </Text>
                      ) : (
                        <Flex align="center" gap="1">
                          {visibleCustomers.map((name) => (
                            <Tooltip key={name} content={name}>
                              <span>
                                <Avatar name={name} size={22} />
                              </span>
                            </Tooltip>
                          ))}
                          {extraCount > 0 ? (
                            <Text size="1" style={{ color: portal.muted }}>
                              +{extraCount} more
                            </Text>
                          ) : null}
                        </Flex>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <RowMenu detailHref={`/intelligence/pain-points/detail?name=${encodeURIComponent(item.topic_name)}`} />
                    </Table.Cell>
                  </Table.Row>
                );
              })}
            </Table.Body>
          </Table.Root>
        ) : null}
      </SurfacePanel>
    </Flex>
  );
}
