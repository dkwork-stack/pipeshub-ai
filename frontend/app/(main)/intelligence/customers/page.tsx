'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Badge, Card, Flex, Table, Text } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import { useCustomers, useSourceConnectors } from '../api';
import { formatCount, formatDate, formatMoney } from '../components/format';
import {
  EmptyState,
  ErrorState,
  FiltersBar,
  LoadingRows,
  PaginationBar,
  PortalHeader,
} from '../components/primitives';

const PAGE_SIZE = 25;

export default function CustomersPage() {
  const [query, setQuery] = useState('');
  const [minArr, setMinArr] = useState('');
  const [connector, setConnector] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);
  const debouncedMinArr = useDebouncedSearch(minArr, 300);
  const minArrNumber = debouncedMinArr === '' ? undefined : Number(debouncedMinArr);

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useCustomers({
    q: debouncedQuery || undefined,
    min_arr: minArrNumber !== undefined && !Number.isNaN(minArrNumber) ? minArrNumber : undefined,
    source_connector: connector || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  return (
    <Flex direction="column" gap="4">
      <PortalHeader
        title="Customers"
        subtitle="Accounts with recorded feature demand, joined with their latest subscription snapshot."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        minArr={minArr}
        onMinArrChange={resetAnd(setMinArr)}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search customer name or ID…"
      />

      <Card size="2">
        {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
        {isLoading && !data ? <LoadingRows rows={8} /> : null}
        {data && data.items.length === 0 ? (
          <EmptyState icon="groups" title="No customers match" description="Try clearing filters." />
        ) : null}
        {data && data.items.length > 0 ? (
          <Table.Root size="2">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>Customer</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">ARR</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">MRR</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Renewal</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Gaps</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Top asks</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {data.items.map((c) => (
                <Table.Row key={c.external_customer_id}>
                  <Table.RowHeaderCell>
                    <Flex direction="column">
                      <Link href={`/intelligence/customers/${encodeURIComponent(c.external_customer_id)}`}>
                        <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
                          {c.customer_name}
                        </Text>
                      </Link>
                      <Text size="1" style={{ color: 'var(--slate-10)' }}>
                        {c.external_customer_id}
                      </Text>
                    </Flex>
                  </Table.RowHeaderCell>
                  <Table.Cell align="right">{formatMoney(c.latest_revenue?.arr)}</Table.Cell>
                  <Table.Cell align="right">{formatMoney(c.latest_revenue?.mrr)}</Table.Cell>
                  <Table.Cell>{formatDate(c.latest_revenue?.renewal_date)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(c.feature_gap_count)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(c.mention_count)}</Table.Cell>
                  <Table.Cell>
                    <Flex gap="1" wrap="wrap">
                      {c.top_insights.length === 0 ? (
                        <Text size="1" style={{ color: 'var(--slate-10)' }}>
                          —
                        </Text>
                      ) : (
                        c.top_insights.map((i) => (
                          <Link
                            key={i.feature_name}
                            href={`/intelligence/feature-gaps/${encodeURIComponent(i.feature_name)}`}
                          >
                            <Badge color="blue" variant="soft" size="1">
                              {i.feature_name} · {i.mention_count}
                            </Badge>
                          </Link>
                        ))
                      )}
                    </Flex>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        ) : null}
      </Card>

      <PaginationBar page={data?.page} onOffsetChange={setOffset} />
    </Flex>
  );
}
