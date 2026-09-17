'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Card, Flex, Table, Text } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import { useFeatureGaps, useSourceConnectors } from '../api';
import { formatCount, formatMoney, formatScore } from '../components/format';
import {
  EmptyState,
  ErrorState,
  FiltersBar,
  LoadingRows,
  PaginationBar,
  PortalHeader,
} from '../components/primitives';

const PAGE_SIZE = 25;

export default function FeatureGapsPage() {
  const [query, setQuery] = useState('');
  const [minArr, setMinArr] = useState('');
  const [connector, setConnector] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);
  const debouncedMinArr = useDebouncedSearch(minArr, 300);
  const minArrNumber = debouncedMinArr === '' ? undefined : Number(debouncedMinArr);

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useFeatureGaps({
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
        title="Feature Gaps"
        subtitle="Features customers asked for that the product does not deliver today, ranked by revenue at stake."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        minArr={minArr}
        onMinArrChange={resetAnd(setMinArr)}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search feature name…"
      />

      <Card size="2">
        {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
        {isLoading && !data ? <LoadingRows rows={8} /> : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            icon="extension"
            title="No feature gaps match"
            description="Try clearing filters, or index more support tickets, CRM notes or call transcripts."
          />
        ) : null}
        {data && data.items.length > 0 ? (
          <Table.Root size="2">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">ARR at stake</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">MRR at stake</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Customers</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Score</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell>Top customers</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {data.items.map((gap) => (
                <Table.Row key={gap.feature_name}>
                  <Table.RowHeaderCell>
                    <Link href={`/intelligence/feature-gaps/${encodeURIComponent(gap.feature_name)}`}>
                      <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
                        {gap.feature_name}
                      </Text>
                    </Link>
                  </Table.RowHeaderCell>
                  <Table.Cell align="right">{formatMoney(gap.total_arr_at_stake)}</Table.Cell>
                  <Table.Cell align="right">{formatMoney(gap.total_mrr_at_stake)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(gap.customer_count)}</Table.Cell>
                  <Table.Cell align="right">{formatCount(gap.mention_count)}</Table.Cell>
                  <Table.Cell align="right">{formatScore(gap.score)}</Table.Cell>
                  <Table.Cell>
                    <Text size="1" style={{ color: 'var(--slate-11)' }}>
                      {gap.top_customers.join(', ') || '—'}
                    </Text>
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
