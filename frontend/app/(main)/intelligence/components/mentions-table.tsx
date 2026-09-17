'use client';

import Link from 'next/link';
import { Badge, Flex, Link as RadixLink, Table, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import type { Mention } from '../types';
import { formatConfidence, formatDate } from './format';
import { EmptyState } from './primitives';

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
                <Link href={`/intelligence/feature-gaps/${encodeURIComponent(m.feature_name)}`}>
                  <Text size="2" weight="medium" style={{ color: 'var(--accent-11)' }}>
                    {m.feature_name}
                  </Text>
                </Link>
              </Table.Cell>
            ) : null}
            {showCustomer ? (
              <Table.Cell>
                <Link href={`/intelligence/customers/${encodeURIComponent(m.external_customer_id)}`}>
                  <Text size="2" style={{ color: 'var(--accent-11)' }}>
                    {m.external_customer_id}
                  </Text>
                </Link>
              </Table.Cell>
            ) : null}
            <Table.Cell style={{ maxWidth: 420 }}>
              <Flex direction="column" gap="1">
                {m.description ? (
                  <Text size="2" style={{ color: 'var(--slate-12)' }}>
                    {m.description}
                  </Text>
                ) : null}
                {m.excerpt ? (
                  <Text
                    size="1"
                    style={{
                      color: 'var(--slate-11)',
                      fontStyle: 'italic',
                      borderLeft: '2px solid var(--slate-6)',
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
                <Badge color="gray" variant="soft" size="1">
                  {m.source_connector}
                </Badge>
                {m.source_type ? (
                  <Text size="1" style={{ color: 'var(--slate-10)' }}>
                    {m.source_type}
                  </Text>
                ) : null}
              </Flex>
            </Table.Cell>
            <Table.Cell align="right">
              <Text size="2">{formatConfidence(m.confidence)}</Text>
            </Table.Cell>
            <Table.Cell>
              <Text size="2" style={{ whiteSpace: 'nowrap' }}>
                {formatDate(m.occurred_at)}
              </Text>
            </Table.Cell>
            <Table.Cell>
              {m.citation_url ? (
                <RadixLink href={m.citation_url} target="_blank" rel="noreferrer" size="2">
                  <Flex align="center" gap="1">
                    <MaterialIcon name="open_in_new" size={14} />
                    Open
                  </Flex>
                </RadixLink>
              ) : (
                <Text size="1" style={{ color: 'var(--slate-10)' }}>
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
