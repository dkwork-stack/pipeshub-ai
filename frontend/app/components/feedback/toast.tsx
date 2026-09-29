'use client';

import React, { useState } from 'react';
import { Flex, Box, Text, IconButton } from '@radix-ui/themes';
import { usePathname } from 'next/navigation';
import { MaterialIcon } from '@/app/components/ui/MaterialIcon';
import { LottieLoader } from '@/app/components/ui/lottie-loader';
import { LapTimerIcon } from '@/app/components/ui/lap-timer-icon';
import type { Toast as ToastType, ToastVariant } from '@/lib/store/toast-store';
import { getToastRenderDescription } from '@/lib/store/toast-store';
import { Link } from '@/lib/navigation';

// ========================================
// Toast Icon Configuration
// ========================================

interface VariantConfig {
  icon: string;
  iconColor: string;
  iconBgColor: string;
}

const VARIANT_CONFIG: Record<ToastVariant, VariantConfig> = {
  loading: {
    icon: 'timer',
    iconColor: 'var(--slate-11)',
    iconBgColor: 'rgba(0, 0, 85, 0.02)',
  },
  success: {
    icon: 'check',
    iconColor: 'var(--accent-11)',
    iconBgColor: 'var(--accent-a2)',
  },
  error: {
    icon: 'error_outline',
    iconColor: 'var(--red-10)',
    iconBgColor: 'var(--olive-3)',
  },
  info: {
    icon: 'info',
    iconColor: 'var(--slate-11)',
    iconBgColor: 'var(--olive-3)',
  },
  warning: {
    icon: 'warning',
    iconColor: 'var(--orange-9)',
    iconBgColor: 'var(--olive-3)',
  },
};

/** Cooper portal toast palette — only applied on /intelligence routes. */
const COOPER_VARIANT_CONFIG: Record<ToastVariant, VariantConfig> = {
  loading: {
    icon: 'timer',
    iconColor: '#2563eb',
    iconBgColor: '#eff6ff',
  },
  success: {
    icon: 'check',
    iconColor: '#16a34a',
    iconBgColor: '#dcfce7',
  },
  error: {
    icon: 'error_outline',
    iconColor: '#dc2626',
    iconBgColor: '#fee2e2',
  },
  info: {
    icon: 'info',
    iconColor: '#2563eb',
    iconBgColor: '#eff6ff',
  },
  warning: {
    icon: 'warning',
    iconColor: '#d97706',
    iconBgColor: '#fef3c7',
  },
};

const COOPER_TOAST_SURFACE = {
  background: '#ffffff',
  border: '1px solid #e8edf5',
  borderRadius: 12,
  boxShadow: '0 1px 2px rgba(23, 32, 51, 0.04), 0 8px 24px rgba(23, 32, 51, 0.10)',
  titleColor: '#172033',
  descriptionColor: '#667085',
} as const;

// ========================================
// Toast Component Props
// ========================================

interface ToastProps {
  toast: ToastType;
  onDismiss: (id: string) => void;
  style?: React.CSSProperties;
}

/** Route wheel events to this pane; the toast stack container does not scroll. */
function handleDescriptionWheel(event: React.WheelEvent<HTMLDivElement>) {
  event.stopPropagation();
}

export function Toast({ toast, onDismiss, style }: ToastProps) {
  const [isHovered, setIsHovered] = useState(false);
  const pathname = usePathname();
  const isCooper = pathname?.startsWith('/intelligence') ?? false;
  const config = (isCooper ? COOPER_VARIANT_CONFIG : VARIANT_CONFIG)[toast.variant];

  const iconName = toast.icon || config.icon;
  const isLoading = toast.variant === 'loading';
  const isExpanded = toast.contentLayout === 'expanded';
  const renderDescription = getToastRenderDescription(toast.id);
  const hasDescription = !!(renderDescription || toast.description);

  const descriptionMaxHeight = isExpanded
    ? 'min(48dvh, 300px)'
    : 'min(36dvh, 220px)';

  return (
    <Box
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: '100%',
        maxWidth: isExpanded
          ? 'min(420px, calc(100vw - 32px))'
          : 'min(340px, calc(100vw - 32px))',
        maxHeight: 'min(72dvh, calc(100dvh - 96px))',
        boxSizing: 'border-box',
        background: isCooper ? COOPER_TOAST_SURFACE.background : 'var(--olive-2)',
        border: isCooper ? COOPER_TOAST_SURFACE.border : '1px solid var(--olive-3)',
        borderRadius: isCooper ? COOPER_TOAST_SURFACE.borderRadius : 'var(--radius-2)',
        boxShadow: isCooper
          ? COOPER_TOAST_SURFACE.boxShadow
          : '0 12px 32px -16px var(--slate-a5, rgba(217, 237, 254, 0.15)), 0 12px 60px 0 var(--Black--a3, rgba(0, 0, 0, 0.15))',
        padding: 'var(--space-3)',
        opacity: toast.isExiting ? 0 : 1,
        transform: toast.isExiting ? 'translateX(100%)' : 'translateX(0)',
        transition: 'opacity 0.3s ease, transform 0.3s ease',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
    >
      <Flex align="start" gap="2" style={{ minWidth: 0 }}>
        <Box
          style={{
            width: '24px',
            height: '24px',
            minWidth: '24px',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: config.iconBgColor,
            borderRadius: isCooper ? 8 : 'var(--radius-2)',
          }}
        >
          {isLoading && !toast.icon ? (
            <LottieLoader variant="loader" size={16} />
          ) : toast.icon === 'lap_timer' ? (
            <LapTimerIcon size={20} color={config.iconColor} />
          ) : (
            <MaterialIcon
              name={iconName}
              size={16}
              color={config.iconColor}
            />
          )}
        </Box>

        <Flex direction="column" gap="1" style={{ flex: 1, minWidth: 0 }}>
          <Text
            size="2"
            weight="medium"
            style={{
              color: isCooper ? COOPER_TOAST_SURFACE.titleColor : 'var(--slate-12)',
              whiteSpace: 'normal',
              lineHeight: 1.35,
              overflowWrap: 'anywhere',
              wordBreak: 'break-word',
              fontFamily: isCooper ? "'Inter', system-ui, sans-serif" : undefined,
            }}
          >
            {toast.title}
          </Text>

          {hasDescription && (
            <Box
              role="region"
              aria-label={toast.title}
              tabIndex={0}
              onWheel={handleDescriptionWheel}
              style={{
                maxHeight: descriptionMaxHeight,
                overflowY: 'auto',
                overflowX: 'hidden',
                scrollbarWidth: 'thin',
                paddingRight: 2,
                width: '100%',
                WebkitOverflowScrolling: 'touch',
                overscrollBehavior: 'contain',
                touchAction: 'pan-y',
              }}
            >
              {renderDescription ? (
                renderDescription()
              ) : (
                <Text
                  size="1"
                  style={{
                    color: isCooper ? COOPER_TOAST_SURFACE.descriptionColor : 'var(--slate-11)',
                    lineHeight: 1.45,
                    fontWeight: 300,
                    letterSpacing: '0.04px',
                    overflowWrap: 'anywhere',
                    wordBreak: 'break-word',
                    whiteSpace: 'pre-line',
                  }}
                >
                  {toast.description}
                </Text>
              )}
            </Box>
          )}

          {toast.action && (
            <Box style={{ marginTop: '6px' }}>
              {toast.action.href ? (
                <Flex align="center" gap="1">
                  {toast.action.icon && (
                    <MaterialIcon
                      name={toast.action.icon}
                      size={14}
                      color={isCooper ? '#2563eb' : 'var(--accent-11)'}
                    />
                  )}
                  <Text size="1" weight="medium" asChild>
                    <Link
                      href={toast.action.href}
                      target={toast.action.openInNewTab ? '_blank' : undefined}
                      rel={toast.action.openInNewTab ? 'noopener noreferrer' : undefined}
                      style={{
                        color: isCooper ? '#2563eb' : 'var(--accent-11)',
                        textDecoration: 'underline',
                        textUnderlineOffset: '2px',
                        cursor: 'pointer',
                      }}
                    >
                      {toast.action.label}
                    </Link>
                  </Text>
                  {toast.action.openInNewTab && (
                    <MaterialIcon
                      name="open_in_new"
                      size={14}
                      color={isCooper ? '#2563eb' : 'var(--accent-11)'}
                    />
                  )}
                </Flex>
              ) : (
                <Flex align="center" justify="center" gap="1" asChild>
                  <button
                    type="button"
                    onClick={toast.action.onClick}
                    style={{
                      height: '24px',
                      padding: '0 8px',
                      border: isCooper ? '1px solid #e8edf5' : '1px solid rgba(0, 6, 46, 0.2)',
                      borderRadius: isCooper ? 8 : '3px',
                      backgroundColor: isCooper ? '#eff6ff' : 'transparent',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    {toast.action.icon && (
                      <MaterialIcon
                        name={toast.action.icon}
                        size={16}
                        color={isCooper ? '#2563eb' : 'var(--slate-11)'}
                      />
                    )}
                    <Text
                      size="1"
                      weight="medium"
                      style={{
                        color: isCooper ? '#2563eb' : 'var(--slate-11)',
                        lineHeight: '16px',
                        letterSpacing: '0.04px',
                      }}
                    >
                      {toast.action.label}
                    </Text>
                  </button>
                </Flex>
              )}
            </Box>
          )}
        </Flex>

        {toast.showCloseButton && (
          <IconButton
            variant="ghost"
            color="gray"
            size="1"
            onClick={(e) => {
              e.stopPropagation();
              onDismiss(toast.id);
            }}
            style={{
              flexShrink: 0,
              opacity: isHovered ? 1 : 0.6,
              transition: 'opacity 0.15s ease',
              cursor: 'pointer',
            }}
          >
            <MaterialIcon name="close" size={18} color={isCooper ? '#667085' : 'var(--slate-11)'} />
          </IconButton>
        )}
      </Flex>
    </Box>
  );
}
