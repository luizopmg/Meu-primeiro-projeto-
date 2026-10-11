import { Env, CrawlerConfig, CrawlerRule } from './types';
import { getCrawlerName } from './crawlers';
import { parsePrice, formatPrice, isPriceAcceptable } from './pricing';
import { log, setLogLevel } from './logger';

// Arquivos que qualquer robô precisa ler de graça para saber as regras do site.
const FREE_PATHS = new Set([
  '/robots.txt', '/sitemap.xml', '/llms.txt', '/llms-full.txt',
  '/security.txt', '/.well-known/security.txt', '/crawlers.json',
]);

let logLevelInitialized = false;
let cachedRulesSource: string | undefined;
let cachedRules: CrawlerConfig | null = null;

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    if (!logLevelInitialized && env.LOG_LEVEL) {
      setLogLevel(env.LOG_LEVEL as Parameters<typeof setLogLevel>[0]);
      logLevelInitialized = true;
    }

    const url = new URL(request.url);
    if (FREE_PATHS.has(url.pathname)) return forward(request, env);

    const crawlerName = getCrawlerName(request.headers.get('User-Agent') || '');
    if (!crawlerName) return forward(request, env); // visitante humano ou buscador comum: sempre livre

    const rule = findRule(crawlerName, env);
    log('info', `Robô de IA: ${crawlerName} → ${rule.action}`, { path: url.pathname });

    if (rule.action === 'allow') return forward(request, env);
    if (rule.action === 'block') return blocked(crawlerName);

    const price = rule.price ?? parseDefaultPrice(env);

    // Fluxo proativo: o robô diz o máximo que aceita pagar.
    const maxHeader = request.headers.get('crawler-max-price');
    if (maxHeader) {
      const offered = parsePrice(maxHeader);
      if (offered !== null && isPriceAcceptable(offered, price)) return charged(await forward(request, env), price, crawlerName, url);
      return paymentRequired(price);
    }

    // Fluxo reativo: o robô repete exatamente o preço que recebeu no 402.
    const exactHeader = request.headers.get('crawler-exact-price');
    if (exactHeader) {
      const exact = parsePrice(exactHeader);
      if (exact !== null && Math.abs(exact - price) < 0.00001) return charged(await forward(request, env), price, crawlerName, url);
      return paymentRequired(price);
    }

    return paymentRequired(price);
  },
};

/** Repassa para o site de verdade. Com ORIGIN_URL, funciona também num endereço workers.dev. */
function forward(request: Request, env: Env): Promise<Response> {
  if (!env.ORIGIN_URL) return fetch(request); // modo rota: o Worker fica na frente do próprio domínio
  const incoming = new URL(request.url);
  const target = new URL(incoming.pathname + incoming.search, env.ORIGIN_URL);
  return fetch(new Request(target.toString(), request));
}

function parseDefaultPrice(env: Env): number {
  const p = parseFloat(env.DEFAULT_PRICE ?? '');
  return Number.isFinite(p) && p > 0 ? p : 0.01;
}

function loadRules(env: Env): CrawlerConfig | null {
  if (env.CRAWLER_RULES === cachedRulesSource) return cachedRules;
  cachedRulesSource = env.CRAWLER_RULES;
  cachedRules = null;
  if (env.CRAWLER_RULES) {
    try {
      cachedRules = JSON.parse(env.CRAWLER_RULES) as CrawlerConfig;
    } catch (e) {
      log('error', 'CRAWLER_RULES não é um JSON válido; usando o padrão (cobrar de todos)', { error: String(e) });
    }
  }
  return cachedRules;
}

function findRule(crawlerName: string, env: Env): CrawlerRule {
  const rules = loadRules(env);
  if (rules) {
    const match = rules.crawlers?.find(r => r.name.toLowerCase() === crawlerName.toLowerCase());
    if (match) return match;
    if (rules.default) {
      const rule: CrawlerRule = { name: 'default', action: rules.default };
      if (rules.defaultPrice !== undefined) rule.price = rules.defaultPrice;
      return rule;
    }
  }
  return { name: crawlerName, action: 'charge' };
}

function paymentRequired(price: number): Response {
  return new Response(`Payment required: this content costs ${formatPrice(price)} per request for AI crawlers.\n`, {
    status: 402,
    headers: {
      'crawler-price': formatPrice(price),
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store',
      'vary': 'User-Agent',
    },
  });
}

function blocked(crawlerName: string): Response {
  return new Response(`Access denied for ${crawlerName}.\n`, {
    status: 403,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store', 'vary': 'User-Agent' },
  });
}

function charged(response: Response, price: number, crawlerName: string, url: URL): Response {
  log('info', `Cobrança aceita: ${formatPrice(price)}`, { crawler: crawlerName, path: url.pathname });
  const headers = new Headers(response.headers);
  headers.set('crawler-charged', formatPrice(price));
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
