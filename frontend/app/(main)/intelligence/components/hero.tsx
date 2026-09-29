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
    <Flex justify="between" align="end" gap="4" wrap="wrap" mb="5" style={{ width: '100%' }}>
      <Flex direction="column" gap="2" style={{ minWidth: 0, flex: '1 1 auto' }}>
        {eyebrow ? (
          <Text
            size="1"
            weight="bold"
            style={{
              color: portal.colors.blue,
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
          <Text
            size="3"
            style={{
              color: portal.muted,
              lineHeight: 1.45,
              whiteSpace: 'nowrap',
            }}
          >
            {subtitle}
          </Text>
        ) : null}
      </Flex>
      {actions}
    </Flex>
  );
}
