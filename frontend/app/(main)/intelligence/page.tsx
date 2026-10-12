'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { Box, Button, Flex, Table, Text } from '@radix-ui/themes';
import { useIntelligenceOverview } from './api';
import {
  Avatar,
  ColumnHeader,
  ConnectorBadges,
  EmptyState,
  ErrorState,
  INTENT_LABELS,
  LastUpdatedBadge,
  LoadingRows,
  MiniBar,
  MixBar,
  PortalHero,
  ScoreBadge,
  StatStrip,
  SurfacePanel,
  TrendIndicator,
  formatCount,
  formatDate,
  intentSegments,
  sentimentSegments,
  formatMoney,
  formatScore,
  portal,
  relativeScore,
  resolveFeatureGapScore,
} from './components';

const linkStyle = { textDecoration: 'none', color: 'inherit' } as const;
const panelGrid = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
  gap: 16,
  width: '100%',
  alignItems: 'stretch',
} as const;
const stretchPanel = {
  minWidth: 0,
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  boxSizing: 'border-box',
} as const;
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

  const maxCustomerArr = useMemo(
    () =>
      data && data.top_customers.length
        ? Math.max(...data.top_customers.map((c) => c.latest_revenue?.arr ?? 0))
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
                hint: 'Estimated monthly impact',
              },
              {
                icon: 'extension',
                color: 'amber',
                label: 'Feature gaps',
                value: formatCount(data.feature_gap_count),
                hint: 'Unique feature requests',
              },
              {
                icon: 'group',
                color: 'pink',
                label: 'Customers',
                value: formatCount(data.customer_count),
                hint: 'Asking for these features',
              },
              {
                icon: 'report_problem',
                color: 'red',
                label: 'Pain points',
                value: formatCount(data.pain_point_count ?? 0),
                hint: 'Distinct problems customers raised',
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

          <Box
            className="intelligence-overview-panels"
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.35fr)',
              gap: 16,
              width: '100%',
              alignItems: 'stretch',
            }}
          >
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
              style={{
                minWidth: 0,
                height: '100%',
                minHeight: '100%',
                alignSelf: 'stretch',
                display: 'flex',
                flexDirection: 'column',
                boxSizing: 'border-box',
              }}
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
                        <Table.Cell align="right">
                          <Flex direction="column" align="end" gap="0">
                            <Text size="2" style={{ color: portal.strong }}>
                              {formatMoney(c.latest_revenue?.arr, true)}
                            </Text>
                            <MiniBar value={c.latest_revenue?.arr ?? 0} max={maxCustomerArr} />
                          </Flex>
                        </Table.Cell>
                        <Table.Cell align="right">
                          <Text size="2" style={{ color: portal.strong }}>
                            {formatCount(c.feature_gap_count)}
                          </Text>
                        </Table.Cell>
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
              style={{
                minWidth: 0,
                height: '100%',
                minHeight: '100%',
                alignSelf: 'stretch',
                display: 'flex',
                flexDirection: 'column',
                boxSizing: 'border-box',
              }}
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
                              <Text size="2" style={{ color: portal.strong }}>
                                {formatMoney(gap.total_arr_at_stake, true)}
                              </Text>
                              <MiniBar value={gap.total_arr_at_stake} max={maxArr} />
                            </Flex>
                          </Table.Cell>
                          <Table.Cell align="right">
                            <Text size="2" style={{ color: portal.strong }}>
                              {formatCount(gap.customer_count)}
                            </Text>
                          </Table.Cell>
                          <Table.Cell align="right">
                            <Text size="2" style={{ color: portal.strong }}>
                              {formatCount(gap.mention_count)}
                            </Text>
                          </Table.Cell>
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
          </Box>

          <Box className="intelligence-overview-panels" style={{ ...panelGrid, marginTop: 16 }}>
            <SurfacePanel
              title="Emerging asks"
              subtitle="Mentions in the last 30 days vs the 30 before"
              icon="trending_up"
              style={stretchPanel}
            >
              {(data.emerging_feature_gaps ?? []).length === 0 ? (
                <EmptyState icon="trending_flat" title="Nothing rising right now" description="Asks appear here when recent demand outpaces the previous month." />
              ) : (
                <Table.Root size="2" style={{ width: '100%' }}>
                  <Table.Header>
                    <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                      <ColumnHeader>Feature</ColumnHeader>
                      <ColumnHeader align="right">Last 30 days</ColumnHeader>
                      <ColumnHeader align="right">ARR</ColumnHeader>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {(data.emerging_feature_gaps ?? []).map((gap) => (
                      <Table.Row key={gap.feature_name}>
                        <Table.RowHeaderCell>
                          <Link href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(gap.feature_name)}`} style={linkStyle}>
                            <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                              {gap.feature_name}
                            </Text>
                          </Link>
                        </Table.RowHeaderCell>
                        <Table.Cell align="right">
                          <TrendIndicator trend={gap.trend} />
                        </Table.Cell>
                        <Table.Cell align="right">
                          <Text size="2" style={{ color: portal.strong }}>
                            {formatMoney(gap.total_arr_at_stake, true)}
                          </Text>
                        </Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>

            <SurfacePanel
              title="At-risk customers"
              subtitle="Churn signals or mostly negative evidence, by ARR"
              icon="warning"
              action={
                <Button asChild size="1" variant="soft" style={portal.button.secondary}>
                  <Link href="/intelligence/customers?at_risk=1" style={linkStyle}>
                    View all
                  </Link>
                </Button>
              }
              style={stretchPanel}
            >
              {(data.at_risk_customers ?? []).length === 0 ? (
                <EmptyState icon="verified_user" title="No at-risk customers" description="No churn signals or predominantly negative evidence." />
              ) : (
                <Table.Root size="2" style={{ width: '100%' }}>
                  <Table.Header>
                    <Table.Row style={{ backgroundColor: portal.colors.tableHeaderBg }}>
                      <ColumnHeader>Customer</ColumnHeader>
                      <ColumnHeader align="right">ARR</ColumnHeader>
                      <ColumnHeader>Signal</ColumnHeader>
                      <ColumnHeader>Last touch</ColumnHeader>
                    </Table.Row>
                  </Table.Header>
                  <Table.Body>
                    {(data.at_risk_customers ?? []).map((c) => (
                      <Table.Row key={c.external_customer_id}>
                        <Table.RowHeaderCell>
                          <Link href={`/intelligence/customers/detail?id=${encodeURIComponent(c.external_customer_id)}`} style={linkStyle}>
                            <Flex align="center" gap="2">
                              <Avatar name={c.customer_name} size={24} />
                              <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                                {c.customer_name}
                              </Text>
                            </Flex>
                          </Link>
                        </Table.RowHeaderCell>
                        <Table.Cell align="right">{formatMoney(c.latest_revenue?.arr, true)}</Table.Cell>
                        <Table.Cell>
                          <Text size="1" style={{ color: portal.signal.negative.fg }}>
                            {c.health && c.health.churn_risk_count > 0
                              ? `${formatCount(c.health.churn_risk_count)} churn signal${c.health.churn_risk_count === 1 ? '' : 's'}`
                              : `${Math.round((c.health?.negative_share ?? 0) * 100)}% negative`}
                          </Text>
                        </Table.Cell>
                        <Table.Cell>
                          <Text size="1" style={{ color: portal.muted, whiteSpace: 'nowrap' }}>
                            {formatDate(c.health?.last_touch_at)}
                          </Text>
                        </Table.Cell>
                      </Table.Row>
                    ))}
                  </Table.Body>
                </Table.Root>
              )}
            </SurfacePanel>
          </Box>

          <SurfacePanel
            title="Voice of the customer"
            subtitle="What kind of asks come in, and how customers feel when they raise them"
            icon="record_voice_over"
            style={{ marginTop: 16 }}
          >
            <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}>
              <Flex direction="column" gap="2">
                <Text size="2" weight="medium" style={{ color: portal.strong }}>
                  Ask type
                </Text>
                <MixBar segments={intentSegments(data.intent_mix, INTENT_LABELS)} />
              </Flex>
              <Flex direction="column" gap="2">
                <Text size="2" weight="medium" style={{ color: portal.strong }}>
                  Sentiment
                </Text>
                <MixBar segments={sentimentSegments(data.tone_mix)} />
              </Flex>
            </Box>
          </SurfacePanel>
        </>
      ) : null}
    </Flex>
  );
}
