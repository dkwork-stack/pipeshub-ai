'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { portal } from './theme';

const NAV = [
  { href: '/intelligence', label: 'Overview', icon: 'insights', exact: true },
  { href: '/intelligence/feature-gaps', label: 'Feature Gaps', icon: 'extension' },
  { href: '/intelligence/customers', label: 'Customers', icon: 'groups' },
] as const;

function isActive(pathname: string, href: string, exact?: boolean) {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function PortalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Flex direction="column" style={{ minHeight: '100%', background: portal.pageBg }}>
      <Box
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 5,
          backdropFilter: 'blur(12px)',
          backgroundColor: 'rgba(245, 254, 251, 0.78)',
          borderBottom: '1px solid var(--slate-5)',
        }}
      >
        <Flex
          align="center"
          justify="between"
          gap="4"
          wrap="wrap"
          px="5"
          style={{ maxWidth: portal.contentMaxWidth, margin: '0 auto', minHeight: 64 }}
        >
          <Flex align="center" gap="2">
            <Box
              style={{
                width: 32,
                height: 32,
                borderRadius: 10,
                display: 'grid',
                placeItems: 'center',
                background: 'linear-gradient(145deg, var(--emerald-4), var(--emerald-7))',
              }}
            >
              <MaterialIcon name="lightbulb" size={18} color="var(--emerald-12)" />
            </Box>
            <Flex direction="column" gap="0">
              <Text
                size="3"
                weight="bold"
                style={{ color: portal.strong, fontFamily: portal.displayFont, letterSpacing: '-0.02em' }}
              >
                Feature Intelligence
              </Text>
              <Text size="1" style={{ color: portal.muted }}>
                Revenue-weighted product gaps
              </Text>
            </Flex>
          </Flex>

          <Flex
            align="center"
            gap="1"
            p="1"
            style={{
              backgroundColor: 'rgba(255,255,255,0.7)',
              border: '1px solid var(--slate-5)',
              borderRadius: 999,
            }}
          >
            {NAV.map((item) => {
              const active = isActive(pathname, item.href, 'exact' in item ? item.exact : false);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  style={{
                    ...portal.navPill,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    textDecoration: 'none',
                    backgroundColor: active ? 'var(--emerald-9)' : 'transparent',
                    color: active ? 'white' : portal.muted,
                    fontWeight: active ? 600 : 500,
                  }}
                >
                  <MaterialIcon name={item.icon} size={16} color={active ? 'white' : undefined} />
                  <Text size="2" weight={active ? 'bold' : 'medium'}>
                    {item.label}
                  </Text>
                </Link>
              );
            })}
          </Flex>
        </Flex>
      </Box>

      <Box px="5" py="6" style={{ maxWidth: portal.contentMaxWidth, width: '100%', margin: '0 auto' }}>
        {children}
      </Box>
    </Flex>
  );
}
