'use client';

import Link from 'next/link';
import { Button, Flex, Table, Text } from '@radix-ui/themes';
import { useIntelligenceOverview } from './api';
import {
  ConnectorBadges,
  EmptyState,
  ErrorState,
  LoadingRows,
  PortalHero,
  StatStrip,
  SurfacePanel,
  formatCount,
  formatDate,
  formatMoney,
  formatScore,
} from './components';

export default function IntelligenceOverviewPage() {
  const { data, error, isLoading, mutate } = useIntelligenceOverview(5);

  return (
    <Flex direction="column">
      <PortalHero
        eyebrow="Customer Feature Intelligence"
        title="Gaps ranked by revenue impact"
        subtitle="See what customers ask for, how much ARR is at stake, and the evidence behind every request."
        actions={
          data?.last_mention_at ? (
            <Text size="2" style={{ color: 'var(--slate-10)' }}>
              Last evidence {formatDate(data.last_mention_at)}
            </Text>
          ) : null
        }
      />

      {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}
      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <StatStrip
            items={[
              {
                icon: 'payments',
                label: 'ARR at stake',
                value: formatMoney(data.total_arr_at_stake, true),
                hint: 'Across customers with at least one gap',
              },
              {
                icon: 'calendar_month',
                label: 'MRR at stake',
                value: formatMoney(data.total_mrr_at_stake, true),
              },
              {
                icon: 'extension',
                label: 'Feature gaps',
                value: formatCount(data.feature_gap_count),
              },
              {
                icon: 'groups',
                label: 'Customers',
                value: formatCount(data.customer_count),
              },
              {
                icon: 'format_quote',
                label: 'Mentions',
                value: formatCount(data.mention_count),
                hint: 'Cited pieces of evidence',
              },
            ]}
          />

          <Flex align="center" gap="2" wrap="wrap" mb="5">
            <Text size="2" style={{ color: 'var(--slate-11)' }}>
              Connected sources
            </Text>
            <ConnectorBadges connectors={data.source_connectors} />
          </Flex>

          <Flex gap="4" wrap="wrap" align="start">
            <SurfacePanel
              title="Top feature gaps"
              action={
                <Button asChild size="1" variant="soft" color="teal">
                  <Link href="/intelligence/feature-gaps">View all</Link>
                </Button>
              }
              style={{ flex: '1 1 480px', minWidth: 0 }}
            >
              {data.top_feature_gaps.length === 0 ? (
                <EmptyState
                  icon="extension"
                  title="No feature gaps yet"
                  description="Upload support tickets, CRM notes or call transcripts to a collection to start seeing gaps."
                />
              ) : (
                <Table.Root size="2">
                  <Table.Header>
                    <Table.Row>
                      <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">ARR</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Customers</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Score</Table.ColumnHeaderCell>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {data.top_feature_gaps.map((gap) => (
                      <Table.Row key={gap.feature_name}>
                        <Table.RowHeaderCell>
                          <Link href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(gap.feature_name)}`}>
                            <Text size="2" weight="medium" style={{ color: 'var(--emerald-11)' }}>
                              {gap.feature_name}
                            </Text>
                          </Link>
                        </Table.RowHeaderCell>
                        <Table.Cell align="right">{formatMoney(gap.total_arr_at_stake, true)}</Table.Cell>
                        <Table.Cell align="right">{formatCount(gap.customer_count)}</Table.Cell>
                        <Table.Cell align="right">{formatCount(gap.mention_count)}</Table.Cell>
                        <Table.Cell align="right">{formatScore(gap.score)}</Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>

            <SurfacePanel
              title="Top customers"
              action={
                <Button asChild size="1" variant="soft" color="teal">
                  <Link href="/intelligence/customers">View all</Link>
                </Button>
              }
              style={{ flex: '1 1 360px', minWidth: 0 }}
            >
              {data.top_customers.length === 0 ? (
                <EmptyState icon="groups" title="No customers yet" />
              ) : (
                <Table.Root size="2">
                  <Table.Header>
                    <Table.Row>
                      <Table.ColumnHeaderCell>Customer</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">ARR</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Gaps</Table.ColumnHeaderCell>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {data.top_customers.map((c) => (
                      <Table.Row key={c.external_customer_id}>
                        <Table.RowHeaderCell>
                          <Link href={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`}>
                            <Text size="2" weight="medium" style={{ color: 'var(--emerald-11)' }}>
                              {c.customer_name}
                            </Text>
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
          </Flex>
        </>
      ) : null}
    </Flex>
  );
}
