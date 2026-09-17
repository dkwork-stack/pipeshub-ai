/**
 * Intelligence Portal Routes
 *
 * Auth/scope-gated proxy in front of the Python intelligence service
 * (`/api/v1/intelligence-portal`). Read-only: the intake/write surface stays
 * on the indexing service (`/api/v1/intelligence`).
 *
 * @module intelligence_portal/routes
 */

import { Router } from 'express';
import { Container } from 'inversify';

import { AuthMiddleware } from '../../../libs/middlewares/auth.middleware';
import { requireScopes } from '../../../libs/middlewares/require-scopes.middleware';
import { OAuthScopeNames } from '../../../libs/enums/oauth-scopes.enum';
import { AppConfig } from '../../tokens_manager/config/config';
import {
  getOverview,
  getSourceConnectors,
  searchFeatureGaps,
  getFeatureGap,
  searchCustomers,
  getCustomer,
  getHealth,
} from '../controller/intelligence-portal.controller';

export function createIntelligencePortalRouter(container: Container): Router {
  const router = Router();
  const authMiddleware = container.get<AuthMiddleware>('AuthMiddleware');
  const appConfig = container.get<AppConfig>('AppConfig');
  const read = requireScopes(OAuthScopeNames.INTELLIGENCE_READ);

  router.get('/health', getHealth(appConfig));

  router.get(
    '/overview',
    authMiddleware.authenticate,
    read,
    getOverview(appConfig),
  );
  router.get(
    '/filters/source-connectors',
    authMiddleware.authenticate,
    read,
    getSourceConnectors(appConfig),
  );

  router.get(
    '/feature-gaps',
    authMiddleware.authenticate,
    read,
    searchFeatureGaps(appConfig),
  );
  router.get(
    '/feature-gaps/:featureName',
    authMiddleware.authenticate,
    read,
    getFeatureGap(appConfig),
  );

  router.get(
    '/customers',
    authMiddleware.authenticate,
    read,
    searchCustomers(appConfig),
  );
  router.get(
    '/customers/:externalCustomerId',
    authMiddleware.authenticate,
    read,
    getCustomer(appConfig),
  );

  return router;
}
