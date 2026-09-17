/**
 * Intelligence Portal proxy controller — forwards portal reads to the Python
 * intelligence service's `/api/v1/intelligence-portal` router
 * (`backend/python/app/api/routes/intelligence_portal/`). Thin-proxy shape
 * borrowed from `skills.controller.ts`: axios with `validateStatus: () => true`
 * so upstream status codes and bodies (404 for unknown gaps/customers, 422 for
 * bad filters) reach the client verbatim.
 *
 * Org scoping happens upstream from the forwarded JWT — this layer never reads
 * or injects `orgId`.
 */

import { Response, NextFunction } from 'express';
import axios, { AxiosRequestConfig, AxiosResponse } from 'axios';

import { AuthenticatedUserRequest } from '../../../libs/middlewares/types';
import { Logger } from '../../../libs/services/logger.service';
import {
  BadGatewayError,
  ServiceUnavailableError,
} from '../../../libs/errors/http.errors';
import { AppConfig } from '../../tokens_manager/config/config';

const logger = Logger.getInstance({ service: 'Intelligence Portal Proxy' });

const PORTAL_BASE = '/api/v1/intelligence-portal';
const UPSTREAM_TIMEOUT_MS = 30_000;

const HOP_BY_HOP_HEADERS = new Set([
  'host',
  'content-length',
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'accept-encoding',
]);

function buildForwardHeaders(
  req: AuthenticatedUserRequest,
): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const [key, value] of Object.entries(req.headers)) {
    if (value === undefined || value === '') continue;
    if (HOP_BY_HOP_HEADERS.has(key.toLowerCase())) continue;
    headers[key] = Array.isArray(value) ? value.join(', ') : value;
  }
  const authorization = req.headers.authorization;
  if (authorization !== undefined && headers.authorization === undefined) {
    headers.authorization = authorization;
  }
  return headers;
}

function mapAxiosError(error: unknown, action: string): Error {
  const err = error as {
    response?: { status: number; data: unknown };
    code?: string;
    message?: string;
  };
  if (err.response !== undefined) {
    const status = String(err.response.status);
    logger.error(`${action} upstream returned ${status}`, { status });
    return new BadGatewayError(`${action} failed (upstream ${status})`);
  }
  logger.error(`${action} upstream unreachable`, {
    code: err.code,
    message: err.message,
  });
  return new ServiceUnavailableError(
    'Customer Feature Intelligence service is unavailable',
  );
}

type PathBuilder = (req: AuthenticatedUserRequest) => string;

function forwardGet(pathBuilder: PathBuilder, action: string) {
  return (appConfig: AppConfig) =>
    async (
      req: AuthenticatedUserRequest,
      res: Response,
      next: NextFunction,
    ): Promise<void> => {
      try {
        const requestConfig: AxiosRequestConfig = {
          url: `${appConfig.intelligenceBackend}${pathBuilder(req)}`,
          method: 'GET',
          params: req.query,
          headers: buildForwardHeaders(req),
          timeout: UPSTREAM_TIMEOUT_MS,
          validateStatus: () => true,
        };
        const response: AxiosResponse = await axios.request(requestConfig);
        res.status(response.status).json(response.data);
      } catch (error) {
        next(mapAxiosError(error, action));
      }
    };
}

const encParam = (value: string | undefined): string =>
  encodeURIComponent(value ?? '');

export const getOverview = forwardGet(
  () => `${PORTAL_BASE}/overview`,
  'Get Intelligence Overview',
);
export const getSourceConnectors = forwardGet(
  () => `${PORTAL_BASE}/filters/source-connectors`,
  'List Intelligence Source Connectors',
);

export const searchFeatureGaps = forwardGet(
  () => `${PORTAL_BASE}/feature-gaps`,
  'Search Feature Gaps',
);
export const getFeatureGap = forwardGet(
  (req) => `${PORTAL_BASE}/feature-gaps/${encParam(req.params.featureName)}`,
  'Get Feature Gap',
);

export const searchCustomers = forwardGet(
  () => `${PORTAL_BASE}/customers`,
  'Search Intelligence Customers',
);
export const getCustomer = forwardGet(
  (req) =>
    `${PORTAL_BASE}/customers/${encParam(req.params.externalCustomerId)}`,
  'Get Intelligence Customer',
);

export const getHealth = forwardGet(
  () => '/health',
  'Intelligence Service Health',
);
