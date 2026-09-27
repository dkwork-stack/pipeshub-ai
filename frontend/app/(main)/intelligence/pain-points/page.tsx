'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Flex, Table, Text } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import { usePainPoints, useSourceConnectors } from '../api';
import {
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  FiltersBar,
  LoadingRows,
  PaginationBar,
  PortalHero,
  SurfacePanel,
  formatCount,
  portal,
} from '../components';

const PAGE_SIZE = 25;

export default function PainPointsPage() {
  const [query, setQuery] = useState('');
  const [connector, setConnector] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);
  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = usePainPoints({
    q: debouncedQuery || undefined,
    source_connector: connector || undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  return (
    <Flex direction="column">
      <PortalHero
        eyebrow="Friction signal"
        title="Pain points"
        subtitle="Problems customers expressed, deduped into taxonomy topics with confidence."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        minArr=""
        onMinArrChange={() => undefined}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search pain point…"
        hideMinArr
      />

      <SurfacePanel>
        {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
        {isLoading && !data ? <LoadingRows rows={8} /> : null}
        {data && data.items.length === 0 ? (
          <EmptyState
            icon="report_problem"
            title="No pain points match"
            description="Try clearing filters, or upload more customer data."
          />
        ) : null}
        {data && data.items.length > 0 ? (
          <Table.Root size="2">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeaderCell>Pain point</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Customers</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                <Table.ColumnHeaderCell align="right">Confidence</Table.ColumnHeaderCell>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {data.items.map((item) => (
                <Table.Row key={item.topic_name}>
                  <Table.RowHeaderCell>
                    <Link href={`/intelligence/pain-points/detail?name=${encodeURIComponent(item.topic_name)}`}>
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
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        ) : null}
        {data ? (
          <PaginationBar page={data.page} onOffsetChange={setOffset} />
        ) : null}
      </SurfacePanel>
    </Flex>
  );
}
