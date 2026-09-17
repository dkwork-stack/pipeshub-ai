'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Badge, Button, Card, Flex, Heading, Select, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useCustomer, useSourceConnectors } from '../../api';
import { formatConfidence, formatCount, formatDate, formatMoney } from '../../components/format';
import { MentionsTable } from '../../components/mentions-table';
import {
  ConnectorBadges,
  EmptyState,
  ErrorState,
  KpiCard,
  LoadingRows,
  PortalHeader,
  isNotFoundError,
} from '../../components/primitives';

const ALL = '__all__';

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const customerId = params?.id ? decodeURIComponent(params.id) : null;
  const [connector, setConnector] = useState('');

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useCustomer(customerId, {
    source_connector: connector || undefined,
  });

  const revenue = data?.latest_revenue ?? null;

  return (
    <Flex direction="column" gap="4">
      <Button asChild size="1" variant="ghost" color="gray" style={{ alignSelf: 'flex-start' }}>
        <Link href="/intelligence/customers">
          <MaterialIcon name="arrow_back" size={14} /> Customers
        </Link>
      </Button>

      <PortalHeader
        title={data?.customer_name ?? customerId ?? 'Customer'}
        subtitle={customerId ? `Customer ID: ${customerId}` : undefined}
      />

      {isNotFoundError(error) ? (
        <EmptyState icon="search_off" title="Customer not found" />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : null}

      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <Flex gap="3" wrap="wrap">
            <KpiCard icon="payments" label="ARR" value={formatMoney(revenue?.arr, true)} hint={revenue ? `via ${revenue.source_connector}` : 'No subscription snapshot'} />
            <KpiCard icon="calendar_month" label="MRR" value={formatMoney(revenue?.mrr, true)} />
            <KpiCard icon="event" label="Renewal" value={formatDate(revenue?.renewal_date)} />
            <KpiCard
              icon="group"
              label="Seats"
              value={revenue?.seats_used != null || revenue?.seats_licensed != null ? `${formatCount(revenue?.seats_used)} / ${formatCount(revenue?.seats_licensed)}` : '—'}
              hint="used / licensed"
            />
            <KpiCard icon="extension" label="Feature gaps" value={formatCount(data.feature_gap_count)} />
            <KpiCard icon="format_quote" label="Mentions" value={formatCount(data.mention_count)} />
          </Flex>

          {revenue && revenue.consumed_features.length > 0 ? (
            <Flex align="center" gap="2" wrap="wrap">
              <Text size="1" style={{ color: 'var(--slate-11)' }}>
                Consumed features:
              </Text>
              {revenue.consumed_features.map((f) => (
                <Badge key={f} color="green" variant="soft" size="1">
                  {f}
                </Badge>
              ))}
            </Flex>
          ) : null}

          <Card size="2">
            <Heading size="3" mb="3">
              Requested features
            </Heading>
            {data.insights.length === 0 ? (
              <EmptyState icon="extension" title="No requests recorded" />
            ) : (
              <Table.Root size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Max confidence</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Last mentioned</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Sources</Table.ColumnHeaderCell>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {data.insights.map((i) => (
                    <Table.Row key={i.feature_name}>
                      <Table.RowHeaderCell>
                        <Link href={`/intelligence/feature-gaps/${encodeURIComponent(i.feature_name)}`}>
                          <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
                            {i.feature_name}
                          </Text>
                        </Link>
                      </Table.RowHeaderCell>
                      <Table.Cell align="right">{formatCount(i.mention_count)}</Table.Cell>
                      <Table.Cell align="right">{formatConfidence(i.max_confidence)}</Table.Cell>
                      <Table.Cell>{formatDate(i.last_mentioned_at)}</Table.Cell>
                      <Table.Cell>
                        <ConnectorBadges connectors={i.source_connectors} />
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
            <MentionsTable mentions={data.mentions} showCustomer={false} />
          </Card>
        </>
      ) : null}
    </Flex>
  );
}
