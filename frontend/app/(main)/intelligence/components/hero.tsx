'use client';

import { Flex, Heading, Text } from '@radix-ui/themes';
import { portal } from './theme';

export function PortalHero({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <Flex justify="between" align="end" gap="4" wrap="wrap" mb="5">
      <Flex direction="column" gap="2" style={{ maxWidth: 720 }}>
        {eyebrow ? (
          <Text
            size="1"
            weight="bold"
            style={{
              color: 'var(--emerald-11)',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {eyebrow}
          </Text>
        ) : null}
        <Heading
          size="8"
          style={{
            color: portal.strong,
            fontFamily: portal.displayFont,
            letterSpacing: '-0.03em',
            lineHeight: 1.05,
          }}
        >
          {title}
        </Heading>
        {subtitle ? (
          <Text size="3" style={{ color: portal.muted, maxWidth: 560, lineHeight: 1.45 }}>
            {subtitle}
          </Text>
        ) : null}
      </Flex>
      {actions}
    </Flex>
  );
}
