'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Flex, Table, Text } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import type { CustomerSummary } from '../types';
import { useCustomers, useSourceConnectors } from '../api';
import {
  Avatar,
  ColumnHeader,
  EmptyState,
  ErrorState,
  ExportButton,
  FiltersBar,
  LoadingRows,
  PaginationBar,
  PortalHero,
  RowIndexBadge,
  RowMenu,
  SortableHeader,
  SurfacePanel,
  TopAsksPills,
  exportRowsToCsv,
  formatCount,
  formatDate,
  formatMoney,
  portal,
  useClientSort,
} from '../components';

const PAGE_SIZE = 25;

type SortKey = 'customer_name' | 'arr' | 'mrr' | 'feature_gap_count' | 'mention_count';

function getSortValue(row: CustomerSummary, key: SortKey): string | number | null | undefined {
  switch (key) {
    case 'arr':
      return row.latest_revenue?.arr;
    case 'mrr':
      return row.latest_revenue?.mrr;
    default:
      return row[key];
  }
}

export default function CustomersPage() {
  const [query, setQuery] = useState('');
  const [connector, setConnector] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useCustomers({
    q: debouncedQuery || undefined,
    source_connector: connector || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const { sorted, sortKey, sortDir, toggleSort } = useClientSort<CustomerSummary, SortKey>(
    data?.items,
    getSortValue,
    'arr',
  );

  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  const handleExport = () => {
    if (!sorted) return;
    exportRowsToCsv(
      'customers.csv',
      [
        { header: 'Customer', accessor: (r: CustomerSummary) => r.customer_name },
        { header: 'Customer ID', accessor: (r: CustomerSummary) => r.external_customer_id },
        { header: 'ARR', accessor: (r: CustomerSummary) => r.latest_revenue?.arr ?? '' },
        { header: 'MRR', accessor: (r: CustomerSummary) => r.latest_revenue?.mrr ?? '' },
        { header: 'Renewal', accessor: (r: CustomerSummary) => r.latest_revenue?.renewal_date ?? '' },
        { header: 'Feature gaps', accessor: (r: CustomerSummary) => r.feature_gap_count },
        { header: 'Mentions', accessor: (r: CustomerSummary) => r.mention_count },
      ],
      sorted,
    );
  };

  return (
    <Flex direction="column">
      <PortalHero
        title="Customers"
        subtitle="Accounts with recorded feature demand, joined with their latest subscription snapshot."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search customer name or ID…"
      />

      <SurfacePanel
        title={`Customers${data ? ` (${formatCount(data.page.total)})` : ''}`}
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
          <EmptyState icon="group" title="No customers match" description="Try clearing filters." />
        ) : null}
        {sorted && sorted.length > 0 ? (
          <Table.Root size="2">
            <Table.Header>
              <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                <ColumnHeader>#</ColumnHeader>
                <SortableHeader label="Customer" sortKey="customer_name" activeKey={sortKey} dir={sortDir} onSort={toggleSort} />
                <SortableHeader label="ARR" sortKey="arr" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="MRR" sortKey="mrr" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <ColumnHeader>Renewal</ColumnHeader>
                <SortableHeader label="Gaps" sortKey="feature_gap_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Mentions" sortKey="mention_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <ColumnHeader>Top asks</ColumnHeader>
                <ColumnHeader>{null}</ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {sorted.map((c, i) => (
                <Table.Row key={c.external_customer_id}>
                  <Table.Cell>
                    <RowIndexBadge index={offset + i + 1} />
                  </Table.Cell>
                  <Table.RowHeaderCell>
                    <Link
                      href={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`}
                      style={{ textDecoration: 'none' }}
                    >
                      <Flex align="center" gap="2">
                        <Avatar name={c.customer_name} size={28} />
                        <Flex direction="column" gap="0">
                          <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                            {c.customer_name}
                          </Text>
                          <Text size="1" style={{ color: portal.muted }}>
                            {c.external_customer_id}
                          </Text>
                        </Flex>
                      </Flex>
                    </Link>
                  </Table.RowHeaderCell>
                  <Table.Cell align="right">{formatMoney(c.latest_revenue?.arr)}</Table.Cell>
                  <Table.Cell align="right">{formatMoney(c.latest_revenue?.mrr)}</Table.Cell>
                  <Table.Cell>{formatDate(c.latest_revenue?.renewal_date)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(c.feature_gap_count)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(c.mention_count)}</Table.Cell>
                  <Table.Cell>
                    <TopAsksPills insights={c.top_insights} />
                  </Table.Cell>
                  <Table.Cell>
                    <RowMenu detailHref={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`} />
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        ) : null}
      </SurfacePanel>
    </Flex>
  );
}
