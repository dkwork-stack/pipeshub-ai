'use client';

import Link from 'next/link';
import { Button, Flex, Table, Text } from '@radix-ui/themes';
import { useIntelligenceOverview } from './api';
import {
  Avatar,
  ConnectorBadges,
  EmptyState,
  ErrorState,
  LastUpdatedBadge,
  LoadingRows,
  PortalHero,
  ScoreBadge,
  StatStrip,
  SurfacePanel,
  formatCount,
  formatMoney,
  portal,
} from './components';

export default function IntelligenceOverviewPage() {
  const { data, error, isLoading, mutate } = useIntelligenceOverview(5);

  return (
    <Flex direction="column">
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
                icon: 'calendar_month',
                color: 'blue',
                label: 'MRR at stake',
                value: formatMoney(data.total_mrr_at_stake, true),
              },
              {
                icon: 'extension',
                color: 'purple',
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
                color: 'amber',
                label: 'Mentions',
                value: formatCount(data.mention_count),
                hint: 'Cited pieces of evidence',
              },
            ]}
          />

          <Flex direction="column" gap="2" mb="5">
            <Text size="2" weight="medium" style={{ color: portal.strong }}>
              Connected sources
            </Text>
            <ConnectorBadges connectors={data.source_connectors} />
          </Flex>

          <Flex gap="4" wrap="wrap" align="start">
            <SurfacePanel
              title="Top feature gaps"
              subtitle="Ranked by ARR at stake"
              icon="emoji_events"
              action={
                <Button asChild size="1" variant="soft" style={portal.button.secondary}>
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
                            <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                              {gap.feature_name}
                            </Text>
                          </Link>
                        </Table.RowHeaderCell>
                        <Table.Cell align="right">{formatMoney(gap.total_arr_at_stake, true)}</Table.Cell>
                        <Table.Cell align="right">{formatCount(gap.customer_count)}</Table.Cell>
                        <Table.Cell align="right">{formatCount(gap.mention_count)}</Table.Cell>
                        <Table.Cell align="right">
                          <ScoreBadge label={gap.score.toFixed(2)} value={gap.score} threshold={0.65} />
                        </Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>

            <SurfacePanel
              title="Top customers"
              subtitle="Ranked by ARR"
              icon="group"
              action={
                <Button asChild size="1" variant="soft" style={portal.button.secondary}>
                  <Link href="/intelligence/customers">View all</Link>
                </Button>
              }
              style={{ flex: '1 1 360px', minWidth: 0 }}
            >
              {data.top_customers.length === 0 ? (
                <EmptyState icon="group" title="No customers yet" />
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
          </Flex>
        </>
      ) : null}
    </Flex>
  );
}
