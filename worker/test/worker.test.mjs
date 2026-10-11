// Testes reais do Worker: rodam o código compilado com Request/Response do Node
// e um "site de origem" falso no lugar do fetch global.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../dist/worker.mjs';

const originCalls = [];
globalThis.fetch = async (req) => {
  const r = req instanceof Request ? req : new Request(req);
  originCalls.push(r.url);
  return new Response('<h1>conteúdo do site</h1>', { status: 200, headers: { 'content-type': 'text/html' } });
};

const env = (extra = {}) => ({ DEFAULT_PRICE: '0.01', LOG_LEVEL: 'error', CRAWLER_RULES: '', ...extra });
const call = (path, headers = {}, e = env()) => worker.fetch(new Request('https://meusite.com' + path, { headers }), e, {});
const GPT = { 'User-Agent': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot' };

test('visitante humano passa de graça', async () => {
  const r = await call('/', { 'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/128.0 Mobile Safari/537.36' });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('crawler-charged'), null);
});

test('robô de IA sem pagamento recebe 402 com o preço', async () => {
  const r = await call('/artigo', GPT);
  assert.equal(r.status, 402);
  assert.equal(r.headers.get('crawler-price'), 'USD 0.01');
});

test('User-Agent em minúsculas também é reconhecido', async () => {
  const r = await call('/', { 'User-Agent': 'claudebot/1.0' });
  assert.equal(r.status, 402);
});

test('crawler-max-price suficiente passa e recebe crawler-charged', async () => {
  const r = await call('/artigo', { ...GPT, 'crawler-max-price': 'USD 0.05' });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('crawler-charged'), 'USD 0.01');
  assert.match(await r.text(), /conteúdo/);
});

test('crawler-max-price abaixo do preço continua 402', async () => {
  const r = await call('/artigo', { ...GPT, 'crawler-max-price': 'USD 0.005' });
  assert.equal(r.status, 402);
});

test('crawler-exact-price igual ao preço passa', async () => {
  const r = await call('/artigo', { ...GPT, 'crawler-exact-price': 'USD 0.01' });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('crawler-charged'), 'USD 0.01');
});

test('robots.txt e llms.txt são sempre livres, mesmo para robôs de IA', async () => {
  for (const p of ['/robots.txt', '/llms.txt']) assert.equal((await call(p, GPT)).status, 200, p);
});

test('regras: block → 403, allow → 200, preço próprio', async () => {
  const rules = JSON.stringify({ default: 'charge', defaultPrice: 0.02, crawlers: [
    { name: 'Bytespider', action: 'block' }, { name: 'GPTBot', action: 'allow' }, { name: 'ClaudeBot', action: 'charge', price: 0.05 } ] });
  const e = env({ CRAWLER_RULES: rules });
  assert.equal((await call('/', { 'User-Agent': 'Bytespider' }, e)).status, 403);
  assert.equal((await call('/', GPT, e)).status, 200);
  assert.equal((await call('/', { 'User-Agent': 'ClaudeBot/1.0' }, e)).headers.get('crawler-price'), 'USD 0.05');
  assert.equal((await call('/', { 'User-Agent': 'PerplexityBot/1.0' }, e)).headers.get('crawler-price'), 'USD 0.02');
});

test('CRAWLER_RULES inválido não derruba o Worker', async () => {
  const r = await call('/', GPT, env({ CRAWLER_RULES: '{isso não é json' }));
  assert.equal(r.status, 402);
});

test('ORIGIN_URL repassa para o site original mantendo caminho e parâmetros', async () => {
  originCalls.length = 0;
  const r = await call('/blog/post?id=7', {}, env({ ORIGIN_URL: 'https://origem.exemplo.com' }));
  assert.equal(r.status, 200);
  assert.equal(originCalls[0], 'https://origem.exemplo.com/blog/post?id=7');
});
