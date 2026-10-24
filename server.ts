import express, { Request, Response, NextFunction } from 'express';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { apiRouter } from './src/server/routes.ts';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;
const HOST = '0.0.0.0';

const WEB_DIR = path.join(__dirname, 'web');
const BUREAU_DIR = path.join(WEB_DIR, 'bureau');
const SHARED_DIR = path.join(WEB_DIR, 'shared');

// Standard middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Security headers middleware matching original ALJ-CRM
app.use((req: Request, res: Response, next: NextFunction) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'same-origin');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }
  next();
});

// Runtime configuration exposed to browser
app.get('/runtime-config.js', (_req: Request, res: Response) => {
  res.setHeader('Content-Type', 'application/javascript; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.send(`window.ALJ_RUNTIME = Object.freeze({
  env: "dev",
  projectId: "demo-alj",
  isAIStudio: true,
  authEmulator: ""
});\n`);
});

// API Routes
app.use('/api', apiRouter);

// Static assets
app.use('/static-web', express.static(SHARED_DIR));
app.use('/annuaire', express.static(WEB_DIR));
app.use('/assets', express.static(path.join(WEB_DIR, 'assets')));
app.use(express.static(path.join(__dirname, 'public')));

// Specific files
app.get('/manifest.webmanifest', (_req: Request, res: Response) => {
  const p = path.join(WEB_DIR, 'manifest.webmanifest');
  if (fs.existsSync(p)) {
    res.setHeader('Content-Type', 'application/manifest+json');
    return res.sendFile(p);
  }
  res.status(404).send('Not found');
});

app.get('/sw.js', (_req: Request, res: Response) => {
  const p = path.join(WEB_DIR, 'sw.js');
  if (fs.existsSync(p)) {
    res.setHeader('Content-Type', 'application/javascript');
    return res.sendFile(p);
  }
  res.status(404).send('Not found');
});

// Health check
app.get('/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    version: '2.7.11',
    service: 'ALJ Escalade Cloud API'
  });
});

// Bureau Portal Routes
app.get(['/bureau', '/bureau/'], (_req: Request, res: Response) => {
  const p = path.join(BUREAU_DIR, 'index.html');
  if (fs.existsSync(p)) return res.sendFile(p);
  res.status(404).send('Bureau index not found');
});

app.get('/bureau/:page', (req: Request, res: Response) => {
  const page = req.params.page;
  const target = path.join(BUREAU_DIR, `${page}.html`);
  if (fs.existsSync(target)) {
    return res.sendFile(target);
  }
  res.status(404).send(`<h1>Page bureau « ${page} » introuvable</h1>`);
});

// Mobile PWAs
app.get('/competitions', (_req: Request, res: Response) => {
  const p = path.join(WEB_DIR, 'competitions.html');
  if (fs.existsSync(p)) return res.sendFile(p);
  res.status(404).send('competitions.html not found');
});

app.get(['/index', '/annuaire'], (_req: Request, res: Response) => {
  const p = path.join(WEB_DIR, 'index.html');
  if (fs.existsSync(p)) return res.sendFile(p);
  res.status(404).send('index.html not found');
});

// Root route
app.get('/', (req: Request, res: Response) => {
  if (req.accepts('html')) {
    return res.redirect('/bureau/');
  }
  res.json({
    service: 'ALJ Escalade Cloud API',
    version: '2.7.11',
    bureau_url: '/bureau/',
    competitions_url: '/competitions',
    annuaire_url: '/index'
  });
});

// Start Server
app.listen(PORT, HOST, () => {
  console.log(`🧗 ALJ Escalade CRM server running on http://${HOST}:${PORT}`);
  console.log(`📌 Portail Bureau: http://${HOST}:${PORT}/bureau/`);
  console.log(`📱 PWA Compétitions: http://${HOST}:${PORT}/competitions`);
});
