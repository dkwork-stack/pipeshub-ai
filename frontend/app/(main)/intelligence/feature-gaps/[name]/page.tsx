'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Button, Card, Flex, Heading, Select, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useFeatureGap, useSourceConnectors } from '../../api';
import { formatCount, formatMoney, formatScore } from '../../components/format';
import { MentionsTable } from '../../components/mentions-table';
import { EmptyState, ErrorState, KpiCard, LoadingRows, PortalHeader, isNotFoundError } from '../../components/primitives';

const ALL = '__all__';

export default function FeatureGapDetailPage() {
  const params = useParams<{ name: string }>();
  const featureName = params?.name ? decodeURIComponent(params.name) : null;

  const [customerId, setCustomerId] = useState('');
  const [connector, setConnector] = useState('');

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useFeatureGap(featureName, {
    customer_id: customerId || undefined,
    source_connector: connector || undefined,
  });

  const notFound = isNotFoundError(error);

  return (
    <Flex direction="column" gap="4">
      <Button asChild size="1" variant="ghost" color="gray" style={{ alignSelf: 'flex-start' }}>
        <Link href="/intelligence/feature-gaps">
          <MaterialIcon name="arrow_back" size={14} /> Feature gaps
        </Link>
      </Button>

      <PortalHeader
        title={featureName ?? 'Feature gap'}
        subtitle="Who is asking for this, how much revenue it represents, and the evidence behind it."
      />

      {notFound ? (
        <EmptyState icon="search_off" title="Feature gap not found" description="It may have been renamed or no longer has any evidence." />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : null}

      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <Flex gap="3" wrap="wrap">
            <KpiCard icon="payments" label="ARR at stake" value={formatMoney(data.total_arr_at_stake, true)} />
            <KpiCard icon="calendar_month" label="MRR at stake" value={formatMoney(data.total_mrr_at_stake, true)} />
            <KpiCard icon="groups" label="Customers" value={formatCount(data.customer_count)} />
            <KpiCard icon="format_quote" label="Mentions" value={formatCount(data.mention_count)} />
            <KpiCard icon="leaderboard" label="Priority score" value={formatScore(data.score)} hint="Revenue × demand" />
          </Flex>

          <Card size="2">
            <Heading size="3" mb="3">
              Affected customers
            </Heading>
            {data.affected_customers.length === 0 ? (
              <EmptyState icon="groups" title="No customers" />
            ) : (
              <Table.Root size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Customer</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">ARR</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">MRR</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell />
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {data.affected_customers.map((c) => (
                    <Table.Row key={c.external_customer_id}>
                      <Table.RowHeaderCell>
                        <Link href={`/intelligence/customers/${encodeURIComponent(c.external_customer_id)}`}>
                          <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
                            {c.customer_name}
                          </Text>
                        </Link>
                      </Table.RowHeaderCell>
                      <Table.Cell align="right">{formatMoney(c.arr)}</Table.Cell>
                      <Table.Cell align="right">{formatMoney(c.mrr)}</Table.Cell>
                      <Table.Cell align="right">{formatCount(c.mention_count)}</Table.Cell>
                      <Table.Cell align="right">
                        <Button
                          size="1"
                          variant={customerId === c.external_customer_id ? 'solid' : 'soft'}
                          color="gray"
                          onClick={() =>
                            setCustomerId(customerId === c.external_customer_id ? '' : c.external_customer_id)
                          }
                        >
                          {customerId === c.external_customer_id ? 'Clear filter' : 'Filter evidence'}
                        </Button>
                      </Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Root>
            )}
          </Card>

          <Card size="2">
            <Flex justify="between" align="center" mb="3" gap="3" wrap="wrap">
              <Heading size="3">Evidence</Heading>
              <Flex gap="2" align="center">
                {customerId ? (
                  <Button size="1" variant="soft" color="gray" onClick={() => setCustomerId('')}>
                    Customer: {customerId} ✕
                  </Button>
                ) : null}
                <Select.Root size="1" value={connector || ALL} onValueChange={(v) => setConnector(v === ALL ? '' : v)}>
                  <Select.Trigger style={{ minWidth: 150 }} />
                  <Select.Content>
                    <Select.Item value={ALL}>All sources</Select.Item>
                    {(connectors ?? []).map((c) => (
                      <Select.Item key={c} value={c}>
                        {c}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </Flex>
            </Flex>
            <MentionsTable mentions={data.mentions} showFeature={false} />
          </Card>
        </>
      ) : null}
    </Flex>
  );
}
