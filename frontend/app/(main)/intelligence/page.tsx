'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { Button, Flex, Table, Text } from '@radix-ui/themes';
import { useIntelligenceOverview } from './api';
import {
  Avatar,
  ColumnHeader,
  ConnectorBadges,
  EmptyState,
  ErrorState,
  LastUpdatedBadge,
  LoadingRows,
  MiniBar,
  PortalHero,
  ScoreBadge,
  StatStrip,
  SurfacePanel,
  formatCount,
  formatMoney,
  formatScore,
  portal,
  relativeScore,
  resolveFeatureGapScore,
} from './components';

const linkStyle = { textDecoration: 'none', color: 'inherit' } as const;
const SCORE_THRESHOLD = 0.65;

export default function IntelligenceOverviewPage() {
  const { data, error, isLoading, mutate } = useIntelligenceOverview(5);

  const maxArr = useMemo(
    () =>
      data && data.top_feature_gaps.length
        ? Math.max(...data.top_feature_gaps.map((g) => g.total_arr_at_stake))
        : 0,
    [data],
  );

  const maxRawScore = useMemo(
    () =>
      data && data.top_feature_gaps.length
        ? Math.max(...data.top_feature_gaps.map((g) => resolveFeatureGapScore(g)))
        : 0,
    [data],
  );

  return (
    <Flex direction="column" style={{ width: '100%', minWidth: 0 }}>
      <PortalHero
        eyebrow={portal.brand.name}
        title="Gaps ranked by revenue impact"
        subtitle="See what customers ask for, how much ARR is at stake, and the evidence behind every request."
        actions={<LastUpdatedBadge date={data?.last_mention_at} />}
      />

      {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <StatStrip
            items={[
              {
                icon: 'payments',
                color: 'green',
                label: 'ARR at stake',
                value: formatMoney(data.total_arr_at_stake, true),
                hint: 'Across customers with at least one gap',
              },
              {
                icon: 'attach_money',
                color: 'purple',
                label: 'MRR at stake',
                value: formatMoney(data.total_mrr_at_stake, true),
              },
              {
                icon: 'extension',
                color: 'amber',
                label: 'Feature gaps',
                value: formatCount(data.feature_gap_count),
              },
              {
                icon: 'group',
                color: 'pink',
                label: 'Customers',
                value: formatCount(data.customer_count),
              },
              {
                icon: 'format_quote',
                color: 'blue',
                label: 'Mentions',
                value: formatCount(data.mention_count),
                hint: 'Cited pieces of evidence',
              },
            ]}
          />

          <SurfacePanel title="Connected sources" style={{ marginBottom: 20 }}>
            <ConnectorBadges connectors={data.source_connectors} />
          </SurfacePanel>

          <Flex gap="4" wrap="wrap" align="stretch" style={{ width: '100%' }}>
            <SurfacePanel
              title="Top customers"
              subtitle="Ranked by ARR"
              icon="group"
              action={
                <Button asChild size="1" variant="soft" style={portal.button.secondary}>
                  <Link href="/intelligence/customers" style={linkStyle}>
                    View all
                  </Link>
                </Button>
              }
              style={{ flex: '1 1 360px', minWidth: 0, height: '100%', display: 'flex', flexDirection: 'column' }}
            >
              {data.top_customers.length === 0 ? (
                <EmptyState icon="group" title="No customers yet" />
              ) : (
                <Table.Root size="2" style={{ width: '100%' }}>
                  <Table.Header>
                    <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                      <ColumnHeader>Customer</ColumnHeader>
                      <ColumnHeader align="right">ARR</ColumnHeader>
                      <ColumnHeader align="right">Gaps</ColumnHeader>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {data.top_customers.map((c) => (
                      <Table.Row key={c.external_customer_id}>
                        <Table.RowHeaderCell>
                          <Link
                            href={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`}
                            style={linkStyle}
                          >
                            <Flex align="center" gap="2">
                              <Avatar name={c.customer_name} size={24} />
                              <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                                {c.customer_name}
                              </Text>
                            </Flex>
                          </Link>
                        </Table.RowHeaderCell>
                        <Table.Cell align="right">{formatMoney(c.latest_revenue?.arr, true)}</Table.Cell>
                        <Table.Cell align="right">{formatCount(c.feature_gap_count)}</Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>

            <SurfacePanel
              title="Top feature gaps"
              subtitle="Ranked by ARR at stake"
              icon="emoji_events"
              action={
                <Button asChild size="1" variant="soft" style={portal.button.secondary}>
                  <Link href="/intelligence/feature-gaps" style={linkStyle}>
                    View all
                  </Link>
                </Button>
              }
              style={{ flex: '1 1 480px', minWidth: 0, height: '100%', display: 'flex', flexDirection: 'column' }}
            >
              {data.top_feature_gaps.length === 0 ? (
                <EmptyState
                  icon="extension"
                  title="No feature gaps yet"
                  description="Upload support tickets, CRM notes or call transcripts to a collection to start seeing gaps."
                />
              ) : (
                <Table.Root size="2" style={{ width: '100%' }}>
                  <Table.Header>
                    <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                      <ColumnHeader>Feature</ColumnHeader>
                      <ColumnHeader align="right">ARR</ColumnHeader>
                      <ColumnHeader align="right">Customers</ColumnHeader>
                      <ColumnHeader align="right">Mentions</ColumnHeader>
                      <ColumnHeader align="right">Score</ColumnHeader>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {data.top_feature_gaps.map((gap) => {
                      const normalized = relativeScore(resolveFeatureGapScore(gap), maxRawScore);
                      return (
                        <Table.Row key={gap.feature_name}>
                          <Table.RowHeaderCell>
                            <Link
                              href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(gap.feature_name)}`}
                              style={linkStyle}
                            >
                              <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                                {gap.feature_name}
                              </Text>
                            </Link>
                          </Table.RowHeaderCell>
                          <Table.Cell align="right">
                            <Flex direction="column" align="end" gap="0">
                              <Text size="2">{formatMoney(gap.total_arr_at_stake, true)}</Text>
                              <MiniBar value={gap.total_arr_at_stake} max={maxArr} />
                            </Flex>
                          </Table.Cell>
                          <Table.Cell align="right">{formatCount(gap.customer_count)}</Table.Cell>
                          <Table.Cell align="right">{formatCount(gap.mention_count)}</Table.Cell>
                          <Table.Cell align="right">
                            <ScoreBadge
                              label={formatScore(normalized)}
                              value={normalized}
                              threshold={SCORE_THRESHOLD}
                            />
                          </Table.Cell>
                        </Table.Row>
                      );
                    })}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>
          </Flex>
        </>
      ) : null}
    </Flex>
  );
}
