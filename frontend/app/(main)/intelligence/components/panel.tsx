'use client';

import { Box, Flex, Heading } from '@radix-ui/themes';
import { portal } from './theme';

export function SurfacePanel({
  title,
  action,
  children,
  style,
}: {
  title?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <Box style={{ ...portal.panel, padding: 20, ...style }}>
      {title ? (
        <Flex justify="between" align="center" mb="4" gap="3" wrap="wrap">
          <Heading
            size="4"
            style={{ color: portal.strong, fontFamily: portal.displayFont, letterSpacing: '-0.02em' }}
          >
            {title}
          </Heading>
          {action}
        </Flex>
      ) : null}
      {children}
    </Box>
  );
}
