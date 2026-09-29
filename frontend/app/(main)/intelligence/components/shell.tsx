'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { useIsMobile } from '@/lib/hooks/use-is-mobile';
import { CooperLogo } from './cooper-logo';
import { portal } from './theme';

const NAV = [
  { href: '/intelligence', label: 'Overview', icon: 'dashboard', exact: true },
  { href: '/intelligence/customers', label: 'Customers', icon: 'group' },
  { href: '/intelligence/feature-gaps', label: 'Feature Gaps', icon: 'extension' },
  { href: '/intelligence/pain-points', label: 'Pain Points', icon: 'report_problem' },
] as const;

function isActive(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavRail() {
  const pathname = usePathname();
  const isMobile = useIsMobile();
  const [hovered, setHovered] = useState(false);
  const expanded = isMobile ? false : hovered;
  const width = expanded ? portal.sidebar.expandedWidth : portal.sidebar.collapsedWidth;

  return (
    <Flex
      direction="column"
      className="intelligence-sidebar"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flexShrink: 0,
        width,
        height: '100%',
        backgroundColor: portal.sidebar.backgroundColor,
        borderRight: `1px solid ${portal.sidebar.border}`,
        transition: 'width 0.2s ease',
        overflow: 'hidden',
        zIndex: 2,
      }}
    >
      <Flex
        align="center"
        px={expanded ? '4' : '2'}
        style={{ height: 64, flexShrink: 0, justifyContent: expanded ? 'flex-start' : 'center' }}
      >
        <Link
          href="/intelligence"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            textDecoration: 'none',
            color: 'inherit',
            minWidth: 0,
          }}
        >
          <CooperLogo size={36} />
          {expanded ? (
            <Text
              size="3"
              weight="bold"
              style={{
                color: portal.sidebar.text,
                fontFamily: portal.displayFont,
                letterSpacing: '-0.02em',
                whiteSpace: 'nowrap',
              }}
            >
              {portal.brand.name}
            </Text>
          ) : null}
        </Link>
      </Flex>

      <Flex direction="column" gap="1" px={expanded ? '3' : '2'} py="2" style={{ flex: 1 }}>
        {NAV.map((item) => {
          const active = isActive(pathname, item.href, 'exact' in item ? item.exact : false);
          return (
            <Tooltip key={item.href} content={item.label} side="right">
              <Link
                href={item.href}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: expanded ? 'flex-start' : 'center',
                  gap: 12,
                  height: 40,
                  borderRadius: 10,
                  padding: expanded ? '0 14px' : '0',
                  textDecoration: 'none',
                  backgroundColor: active ? portal.sidebar.activeBg : 'transparent',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                }}
              >
                <MaterialIcon
                  name={item.icon}
                  size={20}
                  color={active ? 'white' : portal.sidebar.muted}
                />
                {expanded ? (
                  <Text
                    size="2"
                    weight={active ? 'bold' : 'medium'}
                    style={{ color: active ? 'white' : portal.sidebar.text }}
                  >
                    {item.label}
                  </Text>
                ) : null}
              </Link>
            </Tooltip>
          );
        })}
      </Flex>
    </Flex>
  );
}

export function PortalShell({ children }: { children: React.ReactNode }) {
  return (
    <Flex
      className="intelligence-shell"
      style={{
        height: '100%',
        width: '100%',
        minWidth: 0,
        overflow: 'hidden',
        backgroundColor: portal.pageBg,
        fontFamily: portal.displayFont,
        color: portal.strong,
      }}
    >
      <NavRail />
      <Box
        className="no-scrollbar intelligence-content"
        style={{ flex: 1, height: '100%', minWidth: 0, overflowY: 'auto', overflowX: 'hidden' }}
      >
        <Box
          className="intelligence-content-inner"
          px={{ initial: '3', sm: '4', md: '6' }}
          py={{ initial: '4', md: '6' }}
          style={{
            maxWidth: portal.contentMaxWidth,
            width: '100%',
            margin: '0 auto',
            boxSizing: 'border-box',
          }}
        >
          {children}
        </Box>
      </Box>
    </Flex>
  );
}
