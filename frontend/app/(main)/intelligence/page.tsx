'use client';

import Link from 'next/link';
import { Button, Card, Flex, Heading, Table, Text } from '@radix-ui/themes';
import { useIntelligenceOverview } from './api';
import { formatCount, formatDate, formatMoney, formatScore } from './components/format';
import {
  ConnectorBadges,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingRows,
  PortalHeader,
} from './components/primitives';

export default function IntelligenceOverviewPage() {
  const { data, error, isLoading, mutate } = useIntelligenceOverview(5);

  return (
    <Flex direction="column" gap="5">
      <PortalHeader
        title="Overview"
        subtitle="Revenue-weighted view of the feature gaps your customers are asking for, with evidence."
        actions={
          data?.last_mention_at ? (
            <Text size="1" style={{ color: 'var(--slate-10)' }}>
              Last evidence: {formatDate(data.last_mention_at)}
            </Text>
          ) : null
        }
      />

      {error ? <ErrorState error={error} onRetry={() => void mutate()} /> : null}

      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <Flex gap="3" wrap="wrap">
            <KpiCard icon="payments" label="ARR at stake" value={formatMoney(data.total_arr_at_stake, true)} hint="Sum of ARR across customers with at least one gap" />
            <KpiCard icon="calendar_month" label="MRR at stake" value={formatMoney(data.total_mrr_at_stake, true)} />
            <KpiCard icon="extension" label="Feature gaps" value={formatCount(data.feature_gap_count)} />
            <KpiCard icon="groups" label="Customers" value={formatCount(data.customer_count)} />
            <KpiCard icon="format_quote" label="Mentions" value={formatCount(data.mention_count)} hint="Cited pieces of evidence" />
          </Flex>

          <Flex align="center" gap="2" wrap="wrap">
            <Text size="1" style={{ color: 'var(--slate-11)' }}>
              Sources:
            </Text>
            <ConnectorBadges connectors={data.source_connectors} />
          </Flex>

          <Flex gap="4" wrap="wrap" align="start">
            <Card size="2" style={{ flex: '1 1 480px', minWidth: 0 }}>
              <Flex justify="between" align="center" mb="3">
                <Heading size="3">Top feature gaps</Heading>
                <Button asChild size="1" variant="ghost">
                  <Link href="/intelligence/feature-gaps">View all</Link>
                </Button>
              </Flex>
              {data.top_feature_gaps.length === 0 ? (
                <EmptyState icon="extension" title="No feature gaps yet" description="Upload support tickets, CRM notes or call transcripts to a collection to start seeing gaps." />
              ) : (
                <Table.Root size="1">
                  <Table.Header>
                    <Table.Row>
                      <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">ARR at stake</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Customers</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                      <Table.ColumnHeaderCell align="right">Score</Table.ColumnHeaderCell>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {data.top_feature_gaps.map((gap) => (
                      <Table.Row key={gap.feature_name}>
                        <Table.RowHeaderCell>
                          <Link href={`/intelligence/feature-gaps/${encodeURIComponent(gap.feature_name)}`}>
                            <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
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
            </Card>

            <Card size="2" style={{ flex: '1 1 380px', minWidth: 0 }}>
              <Flex justify="between" align="center" mb="3">
                <Heading size="3">Top customers</Heading>
                <Button asChild size="1" variant="ghost">
                  <Link href="/intelligence/customers">View all</Link>
                </Button>
              </Flex>
              {data.top_customers.length === 0 ? (
                <EmptyState icon="groups" title="No customers yet" />
              ) : (
                <Table.Root size="1">
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
                          <Link href={`/intelligence/customers/${encodeURIComponent(c.external_customer_id)}`}>
                            <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
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
            </Card>
          </Flex>
        </>
      ) : null}
    </Flex>
  );
}
