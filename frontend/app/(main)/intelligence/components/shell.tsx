'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

const NAV = [
  { href: '/intelligence', label: 'Overview', icon: 'dashboard', exact: true },
  { href: '/intelligence/feature-gaps', label: 'Feature Gaps', icon: 'extension' },
  { href: '/intelligence/pain-points', label: 'Pain Points', icon: 'report_problem' },
  { href: '/intelligence/customers', label: 'Customers', icon: 'groups' },
] as const;

function isActive(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Icon-only rail by default; hovering anywhere over it expands it in place
 * (absolute overlay, so it never reflows the page content) to reveal labels.
 */
function NavRail() {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);

  return (
    <Box
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
      style={{
        flexShrink: 0,
        width: portal.rail.collapsedWidth,
        height: '100%',
        position: 'relative',
        zIndex: 30,
      }}
    >
      <Flex
        direction="column"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          height: '100%',
          width: expanded ? portal.rail.expandedWidth : portal.rail.collapsedWidth,
          backgroundColor: '#ffffff',
          borderRight: '1px solid var(--slate-4)',
          boxShadow: expanded ? '8px 0 28px rgba(15, 23, 42, 0.10)' : 'none',
          overflow: 'hidden',
          transition: 'width 0.16s ease, box-shadow 0.16s ease',
        }}
      >
        <Flex align="center" gap="3" px="4" style={{ height: 64, flexShrink: 0 }}>
          <Box
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              flexShrink: 0,
              display: 'grid',
              placeItems: 'center',
              background: portal.brand.gradient,
            }}
          >
            <MaterialIcon name={portal.brand.icon} size={19} color="white" />
          </Box>
          {expanded ? (
            <Flex direction="column" gap="0" style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
              <Text
                size="3"
                weight="bold"
                style={{ color: portal.strong, fontFamily: portal.displayFont, letterSpacing: '-0.02em' }}
              >
                {portal.brand.name}
              </Text>
              <Text size="1" style={{ color: portal.muted }}>
                {portal.brand.tagline}
              </Text>
            </Flex>
          ) : null}
        </Flex>

        <Flex direction="column" gap="1" px="2" py="2" style={{ flex: 1 }}>
          {NAV.map((item) => {
            const active = isActive(pathname, item.href, 'exact' in item ? item.exact : false);
            return (
              <Tooltip key={item.href} content={item.label} side="right">
                <Link
                  href={item.href}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    height: 40,
                    borderRadius: 10,
                    padding: '0 14px',
                    textDecoration: 'none',
                    backgroundColor: active ? 'var(--blue-9)' : 'transparent',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                  }}
                >
                  <MaterialIcon name={item.icon} size={20} color={active ? 'white' : portal.muted} />
                  {expanded ? (
                    <Text size="2" weight={active ? 'bold' : 'medium'} style={{ color: active ? 'white' : portal.muted }}>
                      {item.label}
                    </Text>
                  ) : null}
                </Link>
              </Tooltip>
            );
          })}
        </Flex>
      </Flex>
    </Box>
  );
}

export function PortalShell({ children }: { children: React.ReactNode }) {
  return (
    <Flex style={{ height: '100%', width: '100%', overflow: 'hidden', backgroundColor: portal.pageBg }}>
      <NavRail />
      <Box className="no-scrollbar" style={{ flex: 1, height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
        <Box px="6" py="6" style={{ maxWidth: portal.contentMaxWidth, width: '100%', margin: '0 auto' }}>
          {children}
        </Box>
      </Box>
    </Flex>
  );
}
