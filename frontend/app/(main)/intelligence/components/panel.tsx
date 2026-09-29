'use client';

import { Box, Flex, Heading, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

export function SurfacePanel({
  title,
  subtitle,
  icon,
  action,
  children,
  style,
}: {
  title?: string;
  subtitle?: string;
  /** Small colored badge shown before the title (e.g. trophy for "Top feature gaps"). */
  icon?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <Box style={{ ...portal.panel, padding: 20, ...style }}>
      {title ? (
        <Flex justify="between" align="start" mb="4" gap="3" wrap="wrap">
          <Flex align="start" gap="2">
            {icon ? (
              <Flex
                align="center"
                justify="center"
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 9,
                  flexShrink: 0,
                  backgroundColor: portal.colors.blueSoftBg,
                }}
              >
                <MaterialIcon name={icon} size={17} color={portal.colors.blue} />
              </Flex>
            ) : null}
            <Flex direction="column" gap="0">
              <Heading
                size="4"
                style={{ color: portal.strong, fontFamily: portal.displayFont, letterSpacing: '-0.02em' }}
              >
                {title}
              </Heading>
              {subtitle ? (
                <Text size="1" style={{ color: portal.muted }}>
                  {subtitle}
                </Text>
              ) : null}
            </Flex>
          </Flex>
          {action}
        </Flex>
      ) : null}
      {children}
    </Box>
  );
}
