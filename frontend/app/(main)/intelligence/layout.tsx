'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Box, Flex, Text } from '@radix-ui/themes';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';

const NAV = [
  { href: '/intelligence', label: 'Overview', icon: 'insights', exact: true },
  { href: '/intelligence/feature-gaps', label: 'Feature Gaps', icon: 'extension' },
  { href: '/intelligence/customers', label: 'Customers', icon: 'groups' },
] as const;

export default function IntelligenceLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <Flex direction="column" style={{ minHeight: '100%', backgroundColor: 'var(--slate-2)' }}>
      <Box
        style={{
          borderBottom: '1px solid var(--slate-5)',
          backgroundColor: 'var(--color-panel-solid)',
          position: 'sticky',
          top: 0,
          zIndex: 5,
        }}
      >
        <Flex align="center" gap="4" px="5" style={{ height: 48 }}>
          <Flex align="center" gap="2" style={{ marginRight: 'var(--space-4)' }}>
            <MaterialIcon name="lightbulb" size={20} color="var(--accent-9)" />
            <Text size="2" weight="bold" style={{ color: 'var(--slate-12)' }}>
              Customer Feature Intelligence
            </Text>
          </Flex>
          <Flex align="center" gap="1" style={{ height: '100%' }}>
            {NAV.map((item) => {
              const active =
                'exact' in item && item.exact
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    height: '100%',
                    padding: '0 var(--space-3)',
                    borderBottom: `2px solid ${active ? 'var(--accent-9)' : 'transparent'}`,
                    color: active ? 'var(--slate-12)' : 'var(--slate-11)',
                    textDecoration: 'none',
                  }}
                >
                  <MaterialIcon name={item.icon} size={16} />
                  <Text size="2" weight={active ? 'medium' : 'regular'}>
                    {item.label}
                  </Text>
                </Link>
              );
            })}
          </Flex>
        </Flex>
      </Box>
      <Box px="5" py="5" style={{ maxWidth: 1280, width: '100%', margin: '0 auto' }}>
        {children}
      </Box>
    </Flex>
  );
}
