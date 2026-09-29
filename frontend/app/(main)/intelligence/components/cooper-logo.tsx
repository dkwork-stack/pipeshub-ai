'use client';

import Image from 'next/image';
import { portal } from './theme';

/** Cooper brand mark — red square with white stylized C. */
export function CooperLogo({
  size = 36,
  alt = portal.brand.name,
}: {
  size?: number;
  alt?: string;
}) {
  return (
    <Image
      src={portal.brand.logoSrc}
      alt={alt}
      width={size}
      height={size}
      unoptimized
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.28),
        objectFit: 'cover',
        flexShrink: 0,
        display: 'block',
      }}
    />
  );
}
