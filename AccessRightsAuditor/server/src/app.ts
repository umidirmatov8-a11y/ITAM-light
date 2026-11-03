import fs from 'node:fs';
import path from 'node:path';
import express, { NextFunction, Request, Response } from 'express';
import helmet from 'helmet';
import cookieParser from 'cookie-parser';
import { errorHandler, HttpError } from './common/http';
import { authRouter, requireAuth, sessionMiddleware } from './modules/auth/auth';
import { adminRouter } from './modules/admin/admin';
import { referenceRouter } from './modules/reference-data/reference';
import { matrixRouter } from './modules/access-matrix/matrix';
import { sodRouter } from './modules/sod/sod';
import { exceptionsRouter } from './modules/exceptions/exceptions';
import { importsRouter } from './modules/imports/imports';
import { auditsRouter, findingsRouter } from './modules/audits/audits';
import { comparisonsRouter } from './modules/comparisons/comparisons';
import { reportsRouter } from './modules/reports/reports';
import { dashboardRouter } from './modules/dashboard/dashboard';
import { config } from './config';

export function createApp() {
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', false);
  app.use(helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"], scriptSrc: ["'self'"], styleSrc: ["'self'", "'unsafe-inline'"], imgSrc: ["'self'", 'data:'],
        connectSrc: ["'self'"], objectSrc: ["'none'"], frameAncestors: ["'none'"], upgradeInsecureRequests: null,
      },
    },
    hsts: false,
    crossOriginEmbedderPolicy: false,
  }));
  app.use(cookieParser());
  app.use(express.json({ limit: '5mb' }));

  const api = express.Router();
  api.use((_req, res, next) => { res.setHeader('Cache-Control', 'no-store'); next(); });
  // Защита от CSRF: изменяющие запросы должны нести заголовок, который браузер не отправит с чужого сайта без CORS.
  api.use((req: Request, _res: Response, next: NextFunction) => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && req.get('X-ARA-Request') !== '1') return next(new HttpError(403, 'Запрос отклонён (CSRF)'));
    next();
  });
  api.use(sessionMiddleware);
  api.get('/health', (_req, res) => { res.json({ ok: true }); });
  api.use('/auth', authRouter);
  api.use(requireAuth);
  api.use('/admin', adminRouter);
  api.use('/reference', referenceRouter);
  api.use('/matrix', matrixRouter);
  api.use('/sod', sodRouter);
  api.use('/exceptions', exceptionsRouter);
  api.use('/', importsRouter);
  api.use('/audits', auditsRouter);
  api.use('/findings', findingsRouter);
  api.use('/comparisons', comparisonsRouter);
  api.use('/', reportsRouter);
  api.use('/dashboard', dashboardRouter);
  api.use((_req, _res, next) => next(new HttpError(404, 'Метод API не найден')));
  app.use('/api', api);

  // Собранный интерфейс (web/dist) + маршрутизация SPA.
  if (fs.existsSync(config.webDist)) {
    app.use(express.static(config.webDist, { index: false, maxAge: '1h' }));
    app.get(/^\/(?!api\/).*/, (_req, res) => res.sendFile(path.join(config.webDist, 'index.html')));
  } else {
    app.get('/', (_req, res) => res.type('text').send('Интерфейс не собран. Выполните: npm run build'));
  }
  app.use(errorHandler);
  return app;
}
