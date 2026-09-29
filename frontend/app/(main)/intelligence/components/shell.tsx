'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Flex, Text, Tooltip } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

const NAV = [
  { href: '/intelligence', label: 'Overview', icon: 'dashboard', exact: true },
  { href: '/intelligence/feature-gaps', label: 'Feature Gaps', icon: 'extension' },
  { href: '/intelligence/pain-points', label: 'Pain Points', icon: 'report_problem' },
  { href: '/intelligence/customers', label: 'Customers', icon: 'group' },
] as const;

function isActive(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavRail() {
  const pathname = usePathname();

  return (
    <Flex
      direction="column"
      style={{
        flexShrink: 0,
        width: portal.sidebar.width,
        height: '100%',
        backgroundColor: '#ffffff',
        borderRight: `1px solid ${portal.colors.border}`,
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
        <Flex direction="column" gap="0" style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
          <Text size="3" weight="bold" style={{ color: portal.strong, fontFamily: portal.displayFont, letterSpacing: '-0.02em' }}>
            {portal.brand.name}
          </Text>
          <Text size="1" style={{ color: portal.muted }}>
            {portal.brand.tagline}
          </Text>
        </Flex>
      </Flex>

      <Flex direction="column" gap="1" px="3" py="2" style={{ flex: 1 }}>
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
                  backgroundColor: active ? portal.colors.blue : 'transparent',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                }}
              >
                <MaterialIcon name={item.icon} size={20} color={active ? 'white' : portal.muted} />
                <Text size="2" weight={active ? 'bold' : 'medium'} style={{ color: active ? 'white' : portal.muted }}>
                  {item.label}
                </Text>
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
      style={{
        height: '100%',
        width: '100%',
        overflow: 'hidden',
        backgroundColor: portal.pageBg,
        fontFamily: portal.displayFont,
        color: portal.strong,
      }}
    >
      <NavRail />
      <Box className="no-scrollbar" style={{ flex: 1, height: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
        <Box px="6" py="6" style={{ maxWidth: portal.contentMaxWidth, width: '100%', margin: '0 auto' }}>
          {children}
        </Box>
      </Box>
    </Flex>
  );
}
