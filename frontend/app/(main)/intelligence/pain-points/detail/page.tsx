'use client';

/**
 * Pain-point detail. Uses `?name=` because `output: 'export'` disallows
 * dynamic segments without a fixed `generateStaticParams` list.
 *
 * URL: `/intelligence/pain-points/detail?name=<topic>`
 */

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Button, Flex, Select, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { usePainPoint, useSourceConnectors } from '../../api';
import {
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  LoadingRows,
  PortalHero,
  StatStrip,
  SurfacePanel,
  TopicGuidancePanel,
  formatConfidence,
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

function PainPointDetailContent() {
  const searchParams = useSearchParams();
  const topicName = searchParams.get('name')?.trim() || null;
  const [connector, setConnector] = useState('');
  const [minConfidence, setMinConfidence] = useState('');

  const { data: connectors } = useSourceConnectors();
  const { data, error, isLoading, mutate } = usePainPoint(topicName, {
    source_connector: connector || undefined,
    min_confidence: minConfidence ? Number(minConfidence) : undefined,
  });

  if (!topicName) {
    return (
      <EmptyState
        icon="search_off"
        title="Missing pain point name"
        description="Open a pain point from the list to see its detail."
      />
    );
  }

  return (
    <Flex direction="column" gap="4">
      <Button asChild size="1" variant="ghost" color="gray" style={{ alignSelf: 'flex-start' }}>
        <Link href="/intelligence/pain-points">
          <MaterialIcon name="arrow_back" size={14} /> Pain points
        </Link>
      </Button>

      <PortalHero
        eyebrow="Pain point"
        title={topicName}
        subtitle="Who expressed this, the evidence behind it, and guidance for the extractor."
      />

      {isNotFoundError(error) ? (
        <EmptyState icon="search_off" title="Pain point not found" />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void mutate()} />
      ) : null}

      {isLoading && !data ? <LoadingRows rows={4} /> : null}

      {data ? (
        <>
          <StatStrip
            items={[
              { icon: 'group', label: 'Customers', value: formatCount(data.customer_count) },
              { icon: 'format_quote', label: 'Mentions', value: formatCount(data.mention_count) },
              {
                icon: 'verified',
                label: 'Max confidence',
                value: formatConfidence(data.max_confidence),
              },
            ]}
          />

          <SurfacePanel title="Extraction guidance">
            <TopicGuidancePanel kind="pain_point" canonicalName={topicName} />
          </SurfacePanel>

          <SurfacePanel title="Affected customers">
            {data.affected_customers.length === 0 ? (
              <EmptyState icon="group" title="No customers" />
            ) : (
              <Table.Root size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Customer</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">ARR</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Mentions</Table.ColumnHeaderCell>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {data.affected_customers.map((c) => (
                    <Table.Row key={c.external_customer_id}>
                      <Table.RowHeaderCell>
                        <Link href={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`}>
                          <Text size="2" style={{ color: portal.colors.blue }}>
                            {c.customer_name}
                          </Text>
                        </Link>
                      </Table.RowHeaderCell>
                      <Table.Cell align="right">{formatMoney(c.arr, true)}</Table.Cell>
                      <Table.Cell align="right">{formatCount(c.mention_count)}</Table.Cell>
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
                  <Select.Trigger style={{ minWidth: 150, ...portal.input }} />
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
                  <Select.Trigger style={{ minWidth: 130, ...portal.input }} />
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
            {data.mentions.length === 0 ? (
              <EmptyState icon="format_quote" title="No evidence yet" />
            ) : (
              <Table.Root variant="surface" size="1">
                <Table.Header>
                  <Table.Row>
                    <Table.ColumnHeaderCell>Evidence</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Source</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell align="right">Confidence</Table.ColumnHeaderCell>
                    <Table.ColumnHeaderCell>Date</Table.ColumnHeaderCell>
                  </Table.Row>
                </Table.Header>
                <Table.Body>
                  {data.mentions.map((m, idx) => (
                    <Table.Row key={`${m.external_event_id}-${idx}`}>
                      <Table.Cell style={{ maxWidth: 420 }}>
                        <Flex direction="column" gap="1">
                          <Text size="2">{m.summary}</Text>
                          {m.excerpt ? (
                            <Text size="1" style={{ color: portal.muted, fontStyle: 'italic' }}>
                              “{m.excerpt}”
                            </Text>
                          ) : null}
                        </Flex>
                      </Table.Cell>
                      <Table.Cell>
                        <Text size="1">{m.source_connector}</Text>
                      </Table.Cell>
                      <Table.Cell align="right">
                        <ConfidenceBadge value={m.confidence} />
                      </Table.Cell>
                      <Table.Cell>{formatDate(m.occurred_at)}</Table.Cell>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Root>
            )}
          </SurfacePanel>
        </>
      ) : null}
    </Flex>
  );
}

export default function PainPointDetailPage() {
  return (
    <Suspense fallback={<LoadingRows rows={4} />}>
      <PainPointDetailContent />
    </Suspense>
  );
}
