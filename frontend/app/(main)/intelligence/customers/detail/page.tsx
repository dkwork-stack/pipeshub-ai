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
import { Badge, Button, Flex, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useCustomer, useSourceConnectors } from '../../api';
import { MentionsTable } from '../../components/mentions-table';
import {
  ColumnHeader,
  ConfidenceBadge,
  ConnectorBadges,
  EmptyState,
  ErrorState,
  EvidenceFilters,
  LoadingRows,
  PortalHero,
  StatStrip,
  SurfacePanel,
  formatConnectorLabel,
  formatCount,
  formatDate,
  formatMoney,
  isNotFoundError,
  portal,
} from '../../components';

/** Shared column widths so Requested features and Pain points line up. */
const INSIGHT_COLS = {
  name: '34%',
  mentions: '12%',
  confidence: '14%',
  date: '18%',
  sources: '22%',
} as const;

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
                hint: revenue ? `via ${formatConnectorLabel(revenue.source_connector)}` : 'No subscription snapshot',
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
              <Table.Root className="intelligence-insight-table" size="2" style={{ width: '100%' }}>
                <Table.Header>
                  <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                    <ColumnHeader style={{ width: INSIGHT_COLS.name }}>Feature</ColumnHeader>
                    <ColumnHeader align="right" style={{ width: INSIGHT_COLS.mentions }}>
                      Mentions
                    </ColumnHeader>
                    <ColumnHeader align="right" style={{ width: INSIGHT_COLS.confidence }}>
                      Confidence
                    </ColumnHeader>
                    <ColumnHeader style={{ width: INSIGHT_COLS.date }}>Last mentioned</ColumnHeader>
                    <ColumnHeader style={{ width: INSIGHT_COLS.sources }}>Sources</ColumnHeader>
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
                      <Table.Cell>
                        <Text size="2" style={{ whiteSpace: 'nowrap' }}>
                          {formatDate(i.last_mentioned_at)}
                        </Text>
                      </Table.Cell>
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
              <Table.Root className="intelligence-insight-table" size="2" style={{ width: '100%' }}>
                <Table.Header>
                  <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                    <ColumnHeader style={{ width: INSIGHT_COLS.name }}>Pain point</ColumnHeader>
                    <ColumnHeader align="right" style={{ width: INSIGHT_COLS.mentions }}>
                      Mentions
                    </ColumnHeader>
                    <ColumnHeader align="right" style={{ width: INSIGHT_COLS.confidence }}>
                      Confidence
                    </ColumnHeader>
                    <ColumnHeader style={{ width: INSIGHT_COLS.date }}>Last mentioned</ColumnHeader>
                    <ColumnHeader style={{ width: INSIGHT_COLS.sources }}>Sources</ColumnHeader>
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
                      <Table.Cell>
                        <Text size="2" style={{ whiteSpace: 'nowrap' }}>
                          {formatDate(i.last_mentioned_at)}
                        </Text>
                      </Table.Cell>
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
              <EvidenceFilters
                connector={connector}
                onConnectorChange={setConnector}
                connectors={connectors ?? []}
                minConfidence={minConfidence}
                onMinConfidenceChange={setMinConfidence}
              />
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
