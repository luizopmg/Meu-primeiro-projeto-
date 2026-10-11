# Aranha Digital 2.0

App Android que mapeia os links de um site público: você digita o endereço, uma aranha
percorre as páginas e monta um mapa interativo com relatório de problemas
(erros HTTP, links quebrados, páginas lentas, sem título ou sem descrição).
Também verifica se o site publica um `llms.txt` e pode seguir os links dele, e mostra como o site trata
os robôs de IA: o que o robots.txt bloqueia e, se você pedir, o que o servidor responde para cada robô
(entra livre, cobra com HTTP 402 Pay Per Crawl ou barra com 403).

A pasta `worker/` traz o outro lado: um Cloudflare Worker que **você** coloca na frente do seu site
para cobrar (402) ou bloquear (403) robôs de IA. Veja [worker/README.md](worker/README.md).

## Baixar o APK

Abra a aba **Releases** deste repositório e toque em `AranhaDigital.apk`.
Funciona no Android 7.0 ou mais novo. Na primeira instalação o Android pede para
permitir "instalar apps desta fonte" para o navegador ou o app de arquivos.

O APK é gerado automaticamente pelo GitHub Actions a cada envio (`.github/workflows/build-apk.yml`).

## O que tem aqui

| Pasta | Conteúdo |
|---|---|
| `app/` | Projeto Android (Java + WebView). A ponte `AranhaNative` faz os pedidos HTTP, abre e salva arquivos. |
| `web/viewer.html` | A tela do app: mapa, aranha, painéis e o rastreador em JavaScript. |
| `python/crawler.py` | O mesmo rastreador para PC ou Pydroid 3; gera `mapa.json` e `relatorio.csv`. |
| `worker/` | Cloudflare Worker Pay Per Crawl (HTTP 402/403 para robôs de IA), com testes. Baseado em Josusanz/pay-per-crawl-worker (MIT). |
| `icon/` | Ícone da aranha (`make_icon.py` gera os vetores e o SVG). |
| `build.sh` | Copia `web/viewer.html` para dentro do app. |
| `llms.txt` | Resumo deste projeto para assistentes de IA ([llmstxt.org](https://llmstxt.org)). |

## Regras que o rastreador segue

- Só visita páginas públicas do mesmo site (`www.site.com` e `site.com` contam como um).
- Lê e respeita o `robots.txt`, inclusive o `Crawl-delay`; se ele negar acesso, não coleta nada.
- Procura o `/llms.txt` do site e mostra título, resumo e links no Resumo.
- Espera pelo menos 1,5 s entre pedidos e recua quando o servidor responde 429/503.
- Não passa por login, captcha nem proteção anti-robô, e nunca envia cabeçalhos de pagamento.
- O teste de robôs de IA faz só 1 pedido por robô na página inicial, identificado como teste da
  Aranha Digital, e pula os robôs que o robots.txt bloqueia.
