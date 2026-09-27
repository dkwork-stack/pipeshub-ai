'use client';

/**
 * Customer detail. Uses `?id=` because `output: 'export'` disallows
 * dynamic `[id]` segments without a fixed `generateStaticParams` list.
 *
 * URL: `/intelligence/customers/detail?id=<external_customer_id>`
 */

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Badge, Button, Flex, Select, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useCustomer, useSourceConnectors } from '../../api';
import { MentionsTable } from '../../components/mentions-table';
import {
  ConfidenceBadge,
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
  isNotFoundError,
  portal,
} from '../../components';

const ALL = '__all__';
const CONF_OPTIONS = [
  { value: ALL, label: 'All confidence' },
  { value: '0.5', label: '≥ 50%' },
  { value: '0.7', label: '≥ 70%' },
  { value: '0.9', label: '≥ 90%' },
] as const;

function CustomerDetailContent() {
  const searchParams = useSearchParams();
  const customerId = searchParams.get('id')?.trim() || null;
  const [connector, setConnector] = useState('');
  const [minConfidence, setMinConfidence] = useState('');

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = useCustomer(customerId, {
    source_connector: connector || undefined,
    min_confidence: minConfidence ? Number(minConfidence) : undefined,
  });

  const revenue = data?.latest_revenue ?? null;

  if (!customerId) {
    return (
      <EmptyState
        icon="search_off"
        title="Missing customer id"
        description="Open a customer from the list to see its detail."
      />
    );
  }

  return (
    <Flex direction="column" gap="4">
      <Button asChild size="1" variant="ghost" color="gray" style={{ alignSelf: 'flex-start' }}>
        <Link href="/intelligence/customers">
          <MaterialIcon name="arrow_back" size={14} /> Customers
        </Link>
      </Button>

      <PortalHero
        eyebrow="Customer"
        title={data?.customer_name ?? customerId}
        subtitle={`Customer ID: ${customerId}`}
      />

      {isNotFoundError(error) ? (
        <EmptyState icon="search_off" title="Customer not found" />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : null}

      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <StatStrip
            items={[
              {
                icon: 'payments',
                label: 'ARR',
                value: formatMoney(revenue?.arr, true),
                hint: revenue ? `via ${revenue.source_connector}` : 'No subscription snapshot',
              },
              { icon: 'calendar_month', label: 'MRR', value: formatMoney(revenue?.mrr, true) },
              { icon: 'event', label: 'Renewal', value: formatDate(revenue?.renewal_date) },
              {
                icon: 'group',
                label: 'Seats',
                value:
                  revenue?.seats_used != null || revenue?.seats_licensed != null
                    ? `${formatCount(revenue?.seats_used)} / ${formatCount(revenue?.seats_licensed)}`
                    : '—',
                hint: 'used / licensed',
              },
              { icon: 'extension', label: 'Feature gaps', value: formatCount(data.feature_gap_count) },
              { icon: 'format_quote', label: 'Mentions', value: formatCount(data.mention_count) },
            ]}
          />

          {revenue && revenue.consumed_features.length > 0 ? (
            <Flex align="center" gap="2" wrap="wrap" mb="2">
              <Text size="1" style={{ color: portal.muted }}>
                Consumed features:
              </Text>
              {revenue.consumed_features.map((f) => (
                <Badge
                  key={f}
                  variant="soft"
                  size="1"
                  style={{ backgroundColor: portal.colors.blueSoftBg, color: portal.colors.blue }}
                >
                  {f}
                </Badge>
              ))}
            </Flex>
          ) : null}

          <SurfacePanel title="Requested features">
            {data.insights.length === 0 ? (
              <EmptyState icon="extension" title="No requests recorded" />
            ) : (
              <Table.Root size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Confidence</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Last mentioned</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Sources</Table.ColumnHeaderCell>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {data.insights.map((i) => (
                    <Table.Row key={i.feature_name}>
                      <Table.RowHeaderCell>
                        <Link href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(i.feature_name)}`}>
                          <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                            {i.feature_name}
                          </Text>
                        </Link>
                      </Table.RowHeaderCell>
                      <Table.Cell align="right">{formatCount(i.mention_count)}</Table.Cell>
                      <Table.Cell align="right">
                        <ConfidenceBadge value={i.max_confidence} />
                      </Table.Cell>
                      <Table.Cell>{formatDate(i.last_mentioned_at)}</Table.Cell>
                      <Table.Cell>
                        <ConnectorBadges connectors={i.source_connectors} />
                      </Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Root>
            )}
          </SurfacePanel>

          <SurfacePanel title="Pain points">
            {(data.pain_point_insights ?? []).length === 0 ? (
              <EmptyState icon="report_problem" title="No pain points recorded" />
            ) : (
              <Table.Root size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Pain point</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Confidence</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Last mentioned</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Sources</Table.ColumnHeaderCell>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {(data.pain_point_insights ?? []).map((i) => (
                    <Table.Row key={i.topic_name}>
                      <Table.RowHeaderCell>
                        <Link href={`/intelligence/pain-points/detail?name=${encodeURIComponent(i.topic_name)}`}>
                          <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                            {i.topic_name}
                          </Text>
                        </Link>
                      </Table.RowHeaderCell>
                      <Table.Cell align="right">{formatCount(i.mention_count)}</Table.Cell>
                      <Table.Cell align="right">
                        <ConfidenceBadge value={i.max_confidence} />
                      </Table.Cell>
                      <Table.Cell>{formatDate(i.last_mentioned_at)}</Table.Cell>
                      <Table.Cell>
                        <ConnectorBadges connectors={i.source_connectors} />
                      </Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Root>
            )}
          </SurfacePanel>

          <SurfacePanel
            title="Evidence"
            action={
              <Flex gap="2">
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
                <Select.Root
                  size="1"
                  value={minConfidence || ALL}
                  onValueChange={(v) => setMinConfidence(v === ALL ? '' : v)}
                >
                  <Select.Trigger style={{ minWidth: 130 }} />
                  <Select.Content>
                    {CONF_OPTIONS.map((o) => (
                      <Select.Item key={o.value} value={o.value}>
                        {o.label}
                      </Select.Item>
                    ))}
                  </Select.Content>
                </Select.Root>
              </Flex>
            }
          >
            <MentionsTable mentions={data.mentions} showCustomer={false} />
          </SurfacePanel>
        </>
      ) : null}
    </Flex>
  );
}

export default function CustomerDetailPage() {
  return (
    <Suspense fallback={<LoadingRows rows={4} />}>
      <CustomerDetailContent />
    </Suspense>
  );
}
