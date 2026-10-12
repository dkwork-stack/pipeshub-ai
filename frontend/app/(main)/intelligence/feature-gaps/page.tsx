'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Flex, Table, Text, Tooltip } from '@radix-ui/themes';
import { useDebouncedSearch } from '@/knowledge-base/hooks/use-debounced-search';
import type { AskIntent, FeatureGap, TopicStatus } from '../types';
import { useFeatureGaps, useSourceConnectors } from '../api';
import {
  Avatar,
  ColumnHeader,
  EmptyState,
  ErrorState,
  ExportButton,
  FiltersBar,
  INTENT_LABELS,
  LoadingRows,
  MiniBar,
  PaginationBar,
  PortalHero,
  RowIndexBadge,
  RowMenu,
  STATUS_OPTIONS,
  ScoreBadge,
  SelectFilter,
  SortableHeader,
  StatusBadge,
  SurfacePanel,
  TrendIndicator,
  UrgencyBadge,
  exportRowsToCsv,
  formatCount,
  formatMoney,
  formatScore,
  portal,
  relativeScore,
  resolveFeatureGapScore,
  useClientSort,
} from '../components';

const PAGE_SIZE = 25;
const SCORE_THRESHOLD = 0.65;

type SortKey =
  | 'feature_name'
  | 'total_arr_at_stake'
  | 'total_mrr_at_stake'
  | 'customer_count'
  | 'mention_count'
  | 'score'
  | 'recent';

const INTENT_OPTIONS = Object.entries(INTENT_LABELS).map(([value, label]) => ({ value, label }));

function getSortValue(row: FeatureGap, key: SortKey): string | number {
  if (key === 'score') return resolveFeatureGapScore(row);
  if (key === 'recent') return row.trend?.mentions_last_30d ?? 0;
  return row[key];
}

/** Most severe urgency present in the gap's evidence, for an at-a-glance column. */
function topUrgency(gap: FeatureGap): string | null {
  const mix = gap.trend?.urgencies ?? {};
  return (['critical', 'high'] as const).find((u) => (mix[u] ?? 0) > 0) ?? null;
}

export default function FeatureGapsPage() {
  const [query, setQuery] = useState('');
  const [connector, setConnector] = useState('');
  const [status, setStatus] = useState('');
  const [intent, setIntent] = useState('');
  const [offset, setOffset] = useState(0);

  const debouncedQuery = useDebouncedSearch(query, 300);

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useFeatureGaps({
    q: debouncedQuery || undefined,
    source_connector: connector || undefined,
    status: (status || undefined) as TopicStatus | undefined,
    intent: (intent || undefined) as AskIntent | undefined,
    limit: PAGE_SIZE,
    offset,
  });

  const { sorted, sortKey, sortDir, toggleSort } = useClientSort<FeatureGap, SortKey>(
    data?.items,
    getSortValue,
    'total_arr_at_stake',
  );

  const maxArr = useMemo(
    () => (data && data.items.length ? Math.max(...data.items.map((g) => g.total_arr_at_stake)) : 0),
    [data],
  );

  const maxRawScore = useMemo(
    () => (data && data.items.length ? Math.max(...data.items.map((g) => resolveFeatureGapScore(g))) : 0),
    [data],
  );

  const resetAnd = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setOffset(0);
  };

  const handleExport = () => {
    if (!sorted) return;
    exportRowsToCsv(
      'feature-gaps.csv',
      [
        { header: 'Feature', accessor: (r: FeatureGap) => r.feature_name },
        { header: 'ARR at stake', accessor: (r: FeatureGap) => r.total_arr_at_stake },
        { header: 'MRR at stake', accessor: (r: FeatureGap) => r.total_mrr_at_stake },
        { header: 'Customers', accessor: (r: FeatureGap) => r.customer_count },
        { header: 'Mentions', accessor: (r: FeatureGap) => r.mention_count },
        { header: 'Score', accessor: (r: FeatureGap) => r.score },
        { header: 'Status', accessor: (r: FeatureGap) => r.status ?? 'open' },
        { header: 'Mentions last 30d', accessor: (r: FeatureGap) => r.trend?.mentions_last_30d ?? '' },
        { header: 'Mentions prior 30d', accessor: (r: FeatureGap) => r.trend?.mentions_prev_30d ?? '' },
        { header: 'Churn-risk mentions', accessor: (r: FeatureGap) => r.trend?.churn_risk_count ?? '' },
        { header: 'Competitors', accessor: (r: FeatureGap) => (r.trend?.competitors ?? []).join('; ') },
        { header: 'Top customers', accessor: (r: FeatureGap) => r.top_customers.join('; ') },
      ],
      sorted,
    );
  };

  return (
    <Flex direction="column">
      <PortalHero
        title="Feature gaps"
        subtitle="What customers asked for that the product does not deliver today, ranked by revenue at stake."
      />

      <FiltersBar
        query={query}
        onQueryChange={resetAnd(setQuery)}
        connector={connector}
        onConnectorChange={resetAnd(setConnector)}
        connectors={connectors ?? []}
        searchPlaceholder="Search feature name…"
        extra={
          <>
            <SelectFilter value={status} onChange={resetAnd(setStatus)} options={STATUS_OPTIONS} allLabel="Any status" width={170} />
            <SelectFilter value={intent} onChange={resetAnd(setIntent)} options={INTENT_OPTIONS} allLabel="Any ask type" width={200} />
          </>
        }
      />

      <SurfacePanel
        title={`Feature gaps${data ? ` (${formatCount(data.page.total)})` : ''}`}
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
            icon="extension"
            title="No feature gaps match"
            description="Try clearing filters, or index more support tickets, CRM notes or call transcripts."
          />
        ) : null}
        {sorted && sorted.length > 0 ? (
          <Table.Root size="2" style={{ '--table-row-background-color': 'transparent' } as React.CSSProperties}>
            <Table.Header>
              <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                <ColumnHeader>#</ColumnHeader>
                <SortableHeader label="Feature" sortKey="feature_name" activeKey={sortKey} dir={sortDir} onSort={toggleSort} />
                <SortableHeader label="ARR at stake" sortKey="total_arr_at_stake" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="MRR at stake" sortKey="total_mrr_at_stake" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Customers" sortKey="customer_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Mentions" sortKey="mention_count" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="Score" sortKey="score" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <SortableHeader label="30-day trend" sortKey="recent" activeKey={sortKey} dir={sortDir} onSort={toggleSort} align="right" />
                <ColumnHeader>Urgency</ColumnHeader>
                <ColumnHeader>Status</ColumnHeader>
                <ColumnHeader>Top customers</ColumnHeader>
                <ColumnHeader>{null}</ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {sorted.map((gap, i) => {
                const visibleCustomers = gap.top_customers.slice(0, 3);
                const extraCount = gap.top_customers.length - visibleCustomers.length;
                const normalized = relativeScore(resolveFeatureGapScore(gap), maxRawScore);
                return (
                  <Table.Row key={gap.feature_name}>
                    <Table.Cell>
                      <RowIndexBadge index={offset + i + 1} />
                    </Table.Cell>
                    <Table.RowHeaderCell>
                      <Link
                        href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(gap.feature_name)}`}
                        style={{ textDecoration: 'none' }}
                      >
                        <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                          {gap.feature_name}
                        </Text>
                      </Link>
                    </Table.RowHeaderCell>
                    <Table.Cell align="right">
                      <Flex direction="column" align="end" gap="0">
                        <Text size="2">{formatMoney(gap.total_arr_at_stake)}</Text>
                        <MiniBar value={gap.total_arr_at_stake} max={maxArr} />
                      </Flex>
                    </Table.Cell>
                    <Table.Cell align="right">{formatMoney(gap.total_mrr_at_stake)}</Table.Cell>
                    <Table.Cell align="right">{formatCount(gap.customer_count)}</Table.Cell>
                    <Table.Cell align="right">{formatCount(gap.mention_count)}</Table.Cell>
                    <Table.Cell align="right">
                      <ScoreBadge label={formatScore(normalized)} value={normalized} threshold={SCORE_THRESHOLD} />
                    </Table.Cell>
                    <Table.Cell align="right">
                      <TrendIndicator trend={gap.trend} />
                    </Table.Cell>
                    <Table.Cell>
                      {topUrgency(gap) ? (
                        <UrgencyBadge urgency={topUrgency(gap) ?? undefined} />
                      ) : (
                        <Text size="1" style={{ color: portal.muted }}>
                          —
                        </Text>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <StatusBadge status={gap.status} />
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
                      <RowMenu detailHref={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(gap.feature_name)}`} />
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
