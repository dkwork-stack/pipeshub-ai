'use client';

import Link from 'next/link';
import { Flex, Link as RadixLink, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { Mention } from '../types';
import { ConfidenceBadge } from './confidence-badge';
import { formatConnectorLabel, SourceConnectorIcon } from './connector-display';
import { formatDate } from './format';
import { EmptyState } from './states';
import { portal } from './theme';

export function MentionsTable({
  mentions,
  showCustomer = true,
  showFeature = true,
}: {
  mentions: Mention[];
  showCustomer?: boolean;
  showFeature?: boolean;
}) {
  if (mentions.length === 0) {
    return (
      <EmptyState
        icon="format_quote"
        title="No evidence yet"
        description="Mentions appear here once connectors or uploads have been indexed for this selection."
      />
    );
  }

  return (
    <Table.Root variant="surface" size="1">
      <Table.Header>
        <Table.Row>
          {showFeature ? <Table.ColumnHeaderCell>Feature</Table.ColumnHeaderCell> : null}
          {showCustomer ? <Table.ColumnHeaderCell>Customer</Table.ColumnHeaderCell> : null}
          <Table.ColumnHeaderCell>Evidence</Table.ColumnHeaderCell>
          <Table.ColumnHeaderCell>Source</Table.ColumnHeaderCell>
          <Table.ColumnHeaderCell align="right">Confidence</Table.ColumnHeaderCell>
          <Table.ColumnHeaderCell>Date</Table.ColumnHeaderCell>
          <Table.ColumnHeaderCell>Citation</Table.ColumnHeaderCell>
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {mentions.map((m, idx) => (
          <Table.Row key={`${m.external_customer_id}-${m.feature_name}-${m.external_event_id ?? idx}`}>
            {showFeature ? (
              <Table.Cell>
                <Link href={`/intelligence/feature-gaps/detail?name=${encodeURIComponent(m.feature_name)}`}>
                  <Text size="2" weight="medium" style={{ color: portal.colors.blue }}>
                    {m.feature_name}
                  </Text>
                </Link>
              </Table.Cell>
            ) : null}
            {showCustomer ? (
              <Table.Cell>
                <Link href={`/intelligence/customers/detail?id=${encodeURIComponent(m.external_customer_id)}`}>
                  <Text size="2" style={{ color: portal.colors.blue }}>
                    {m.external_customer_id}
                  </Text>
                </Link>
              </Table.Cell>
            ) : null}
            <Table.Cell style={{ maxWidth: 420 }}>
              <Flex direction="column" gap="1">
                {m.description ? (
                  <Text size="2" style={{ color: portal.strong }}>
                    {m.description}
                  </Text>
                ) : null}
                {m.excerpt ? (
                  <Text
                    size="1"
                    style={{
                      color: portal.muted,
                      fontStyle: 'italic',
                      borderLeft: `2px solid ${portal.colors.border}`,
                      paddingLeft: 'var(--space-2)',
                    }}
                  >
                    “{m.excerpt}”
                  </Text>
                ) : null}
              </Flex>
            </Table.Cell>
            <Table.Cell>
              <Flex direction="column" gap="1">
                <Flex
                  align="center"
                  gap="1"
                  style={{
                    ...portal.input,
                    borderRadius: 999,
                    padding: '2px 8px',
                    width: 'fit-content',
                  }}
                >
                  <SourceConnectorIcon connector={m.source_connector} size={14} />
                  <Text size="1" weight="medium" style={{ color: portal.strong }}>
                    {formatConnectorLabel(m.source_connector)}
                  </Text>
                </Flex>
                {m.source_type ? (
                  <Text size="1" style={{ color: portal.muted }}>
                    {m.source_type}
                  </Text>
                ) : null}
              </Flex>
            </Table.Cell>
            <Table.Cell align="right">
              <ConfidenceBadge value={m.confidence} />
            </Table.Cell>
            <Table.Cell>
              <Text size="2" style={{ whiteSpace: 'nowrap' }}>
                {formatDate(m.occurred_at)}
              </Text>
            </Table.Cell>
            <Table.Cell>
              {m.citation_url ? (
                <RadixLink href={m.citation_url} target="_blank" rel="noreferrer" size="2" style={{ color: portal.colors.blue }}>
                  <Flex align="center" gap="1">
                    <MaterialIcon name="open_in_new" size={14} color={portal.colors.blue} />
                    Open
                  </Flex>
                </RadixLink>
              ) : (
                <Text size="1" style={{ color: portal.muted }}>
                  {m.external_event_id ?? '—'}
                </Text>
              )}
            </Table.Cell>
          </Table.Row>
        ))}
      </Table.Body>
    </Table.Root>
  );
}
