'use client';

import { Badge, Button, Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { ErrorType, isProcessedError } from '@/lib/api';
import { portal } from './theme';

export function isNotFoundError(error: unknown): boolean {
  return isProcessedError(error) && (error.type === ErrorType.NOT_FOUND || error.statusCode === 404);
}

function errorMessage(error: unknown): string {
  if (isProcessedError(error)) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong while loading intelligence data.';
}

export function EmptyState({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description?: string;
}) {
  return (
    <Flex direction="column" align="center" justify="center" gap="2" style={{ padding: 'var(--space-8) 0' }}>
      <MaterialIcon name={icon} size={40} color="var(--slate-8)" />
      <Text size="3" weight="medium" style={{ color: portal.strong }}>
        {title}
      </Text>
      {description ? (
        <Text size="2" style={{ color: portal.muted, textAlign: 'center', maxWidth: 420 }}>
          {description}
        </Text>
      ) : null}
    </Flex>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Flex direction="column" align="center" justify="center" gap="3" style={{ padding: 'var(--space-8) 0' }}>
      <MaterialIcon name="error" size={40} color="var(--red-9)" />
      <Text size="2" style={{ color: 'var(--red-11)', textAlign: 'center' }}>
        {errorMessage(error)}
      </Text>
      {onRetry ? (
        <Button variant="soft" color="gray" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </Flex>
  );
}

export function LoadingRows({ rows = 5 }: { rows?: number }) {
  return (
    <Flex direction="column" gap="2" style={{ padding: 'var(--space-3) 0' }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{
            height: 36,
            borderRadius: 10,
            backgroundColor: 'var(--emerald-3)',
            opacity: 1 - i * 0.12,
          }}
        />
      ))}
    </Flex>
  );
}

export function ConnectorBadges({ connectors }: { connectors: string[] }) {
  if (connectors.length === 0) return <Text size="1" style={{ color: 'var(--slate-10)' }}>—</Text>;
  return (
    <Flex gap="1" wrap="wrap">
      {connectors.map((c) => (
        <Badge key={c} color="teal" variant="soft" size="1">
          {c}
        </Badge>
      ))}
    </Flex>
  );
}
