# Pay Per Crawl Worker (versão Aranha Digital)

Cloudflare Worker que fica na frente do seu site e decide o que fazer quando um **robô de IA**
(GPTBot, ClaudeBot, PerplexityBot…) pede uma página:

| Situação | Resposta |
|---|---|
| Visitante humano ou buscador comum (Googlebot, Bingbot) | passa livre |
| Robô de IA sem cabeçalho de pagamento | `402 Payment Required` + `crawler-price: USD 0.01` |
| Robô envia `crawler-max-price` ≥ preço, ou `crawler-exact-price` = preço | passa + `crawler-charged` |
| Robô na lista de bloqueio | `403` |
| Robô na lista de liberação | passa livre |
| `/robots.txt`, `/llms.txt`, `/sitemap.xml` | sempre livres, para qualquer robô |

Baseado no [pay-per-crawl-worker](https://github.com/Josusanz/pay-per-crawl-worker) de Josu Sanz (MIT).
Esta versão tira a página de simulação (`demo.ts`) e mantém só o Worker real.

> **Importante:** o Worker fala o protocolo HTTP 402, mas **não recebe dinheiro sozinho**.
> O pagamento de verdade depende do Pay Per Crawl oficial da Cloudflare (em beta fechado)
> e das empresas de IA passarem a enviar pagamentos. Hoje, na prática, ele bloqueia os robôs
> que não pagam e deixa registrado o preço que você cobra.

## O que mudou em relação ao original

- 8 robôs novos: Claude-User, Claude-SearchBot, Meta-ExternalAgent, Meta-ExternalFetcher,
  Perplexity-User, MistralAI-User, DuckAssistBot e CCBot (Common Crawl).
- O User-Agent é comparado sem diferenciar maiúsculas de minúsculas.
- `llms.txt` e `llms-full.txt` liberados para todos, junto com o `robots.txt`.
- `ORIGIN_URL`: permite testar num endereço `*.workers.dev` repassando para o site original.
  No original, publicar sem rota fazia o Worker chamar a si mesmo.
- O JSON de regras é lido uma vez só, e um JSON inválido gera um aviso no log em vez de falhar em silêncio.
- As respostas 402 e 403 têm texto explicativo, `cache-control: no-store` e `vary: User-Agent`.
- Testes automáticos (`npm test`) rodam no GitHub a cada envio.

**Limite conhecido:** `Google-Extended` e `Applebot-Extended` não aparecem no User-Agent. São só
nomes usados no robots.txt, porque o Google e a Apple visitam com Googlebot e Applebot. Para eles, use o robots.txt:

```
User-agent: Google-Extended
Disallow: /
```

## Publicar

### Opção A: pelo celular, com o GitHub Actions
1. Crie uma conta na Cloudflare e coloque seu site nela.
2. Em *My Profile → API Tokens*, crie um token com o modelo **Edit Cloudflare Workers**.
3. No GitHub: *Settings → Secrets and variables → Actions → New repository secret*:
   - `CLOUDFLARE_API_TOKEN`: o token
   - `CLOUDFLARE_ACCOUNT_ID`: o ID da conta (aparece na página inicial da Cloudflare)
4. Edite `worker/wrangler.toml`: tire o `#` de `routes` e coloque seu domínio, **ou**
   preencha `ORIGIN_URL` com o endereço do seu site.
5. Aba *Actions → Publicar Worker → Run workflow*.

### Opção B: no computador
```bash
cd worker
npm install
npm test               # roda os testes
npx wrangler deploy
```

## Regras por robô

Copie `crawler-rules.example.json`, ajuste e coloque o conteúdo em `CRAWLER_RULES`
(em `wrangler.toml`, ou como secret: `npx wrangler secret put CRAWLER_RULES`).

```json
{
  "default": "charge",
  "defaultPrice": 0.01,
  "crawlers": [
    { "name": "Bytespider", "action": "block" },
    { "name": "GPTBot", "action": "charge", "price": 0.01 },
    { "name": "ClaudeBot", "action": "charge", "price": 0.05 }
  ]
}
```

Ações: `charge` (cobra; sem pagamento responde 402), `allow` (libera) e `block` (403).

## Conferir se funcionou

Abra o app **Aranha Digital**, digite o seu site, ligue **"Testar como robôs de IA são recebidos"**
e rastreie. Na aba Resumo, a seção *Robôs de IA* mostra, para cada robô, se ele entra livre,
paga (402, com o preço) ou é bloqueado (403).
