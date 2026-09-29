'use client';

import { Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { ConnectorIcon, resolveConnectorType } from '@/app/components/ui/ConnectorIcon';
import { portal } from './theme';

const CONNECTOR_LABELS: Record<string, string> = {
  file_upload: 'File upload',
  'file-upload': 'File upload',
  fileupload: 'File upload',
};

/** Human-readable label — never show raw snake_case like `file_upload`. */
export function formatConnectorLabel(raw: string): string {
  if (!raw) return '—';
  const normalized = raw.toLowerCase().replace(/[-\s]+/g, '_');
  if (CONNECTOR_LABELS[normalized] || CONNECTOR_LABELS[raw]) {
    return CONNECTOR_LABELS[normalized] ?? CONNECTOR_LABELS[raw];
  }
  return raw
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function isFileUpload(raw: string): boolean {
  const n = raw.toLowerCase().replace(/[-\s]+/g, '_');
  return n === 'file_upload' || n === 'fileupload';
}

/** Brand SVG when known; Material upload icon for file uploads. */
export function SourceConnectorIcon({
  connector,
  size = 15,
}: {
  connector: string;
  size?: number;
}) {
  if (isFileUpload(connector)) {
    return <MaterialIcon name="upload_file" size={size} color={portal.colors.blue} />;
  }
  return <ConnectorIcon type={resolveConnectorType(connector)} size={size} color={portal.muted} />;
}

export function ConnectorBadges({ connectors }: { connectors: string[] }) {
  if (connectors.length === 0) return <Text size="1" style={{ color: portal.muted }}>—</Text>;
  return (
    <Flex gap="2" wrap="wrap">
      {connectors.map((c) => (
        <Tooltip key={c} content={formatConnectorLabel(c)}>
          <Flex
            align="center"
            gap="2"
            style={{
              ...portal.input,
              borderRadius: 999,
              padding: '6px 12px',
            }}
          >
            <SourceConnectorIcon connector={c} size={16} />
            <Text size="1" weight="medium" style={{ color: portal.strong }}>
              {formatConnectorLabel(c)}
            </Text>
          </Flex>
        </Tooltip>
      ))}
    </Flex>
  );
}
