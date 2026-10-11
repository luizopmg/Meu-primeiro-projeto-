"""Aranha Digital 2.0 — rastreador educado de páginas públicas de um site.

Instale:  pip install requests beautifulsoup4
Execute:  python crawler.py                       (pergunta a URL)
          python crawler.py https://site.com -p 60 -d 3
Gera:     mapa.json       (importe em aranha.html)
          relatorio.csv   (abre no Excel / Planilhas)

Regras que ele segue sozinho:
  - só visita o mesmo site (www.site.com e site.com contam como o mesmo);
  - lê e respeita o robots.txt, inclusive o Crawl-delay;
  - espera entre pedidos e recua quando o servidor pede (429/503);
  - não tenta passar por login, captcha ou bloqueio anti-robô.
Ctrl+C a qualquer momento salva o que já foi coletado.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Faltam pacotes. Rode:  pip install requests beautifulsoup4")

try:  # lxml é opcional e bem mais rápido
    import lxml  # noqa: F401
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"

VERSION = "2.0"
USER_AGENT = f"AranhaDigital/{VERSION} (rastreador educacional; respeita robots.txt)"
MAX_BYTES = 3_000_000  # não baixa páginas maiores que ~3 MB
SKIP_EXT = re.compile(
    r"\.(jpe?g|png|gif|webp|svg|ico|bmp|tiff?|pdf|zip|rar|7z|gz|tar|mp[34]|m4a|wav|ogg|"
    r"avi|mov|mkv|webm|exe|apk|dmg|iso|docx?|xlsx?|pptx?|odt|csv|xml|json|css|js|woff2?|ttf)$",
    re.I,
)
TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|igshid)$", re.I)


# ----------------------------------------------------------------------------- URLs
def site_key(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def normalize(url: str, keep_query: bool = False) -> str | None:
    """Deixa a URL num formato único para não visitar a mesma página duas vezes."""
    try:
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    host = p.hostname.lower()
    if p.port and not ((p.scheme == "http" and p.port == 80) or (p.scheme == "https" and p.port == 443)):
        host = f"{host}:{p.port}"
    path = re.sub(r"/{2,}", "/", p.path or "/")
    query = ""
    if keep_query and p.query:
        pairs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)]
        query = urlencode(sorted(pairs))
    return urlunparse((p.scheme.lower(), host, path, "", query, ""))


# ----------------------------------------------------------------------------- robots
class Robots:
    def __init__(self, session: requests.Session, base: str):
        self.parser = RobotFileParser()
        self.allow_all = self.deny_all = False
        self.sitemaps: list[str] = []
        url = f"{base}/robots.txt"
        try:
            r = session.get(url, timeout=12)
        except requests.RequestException as exc:
            raise RuntimeError(f"Não foi possível ler {url} ({exc}). Parando por precaução.") from exc
        if r.status_code in (401, 403):
            self.deny_all = True  # padrão da especificação: acesso negado = não rastrear
        elif r.status_code >= 400:
            self.allow_all = True  # sem robots.txt = tudo liberado
        else:
            self.parser.parse(r.text.splitlines())
            self.sitemaps = list(self.parser.site_maps() or [])

    def can_fetch(self, url: str) -> bool:
        if self.deny_all:
            return False
        return True if self.allow_all else self.parser.can_fetch(USER_AGENT, url)

    def crawl_delay(self) -> float | None:
        if self.allow_all or self.deny_all:
            return None
        d = self.parser.crawl_delay(USER_AGENT)
        return float(d) if d is not None else None


# ----------------------------------------------------------------------------- coleta
class Crawler:
    def __init__(self, start: str, max_pages: int, max_depth: int, delay: float,
                 links_per_page: int, keep_query: bool, use_sitemap: bool):
        self.start = normalize(start, keep_query)
        if not self.start:
            raise ValueError("Informe um endereço válido começando com http:// ou https://")
        self.max_pages, self.max_depth = max_pages, max_depth
        self.links_per_page, self.keep_query = links_per_page, keep_query
        self.site = site_key(urlparse(self.start).netloc)
        p = urlparse(self.start)
        self.base = f"{p.scheme}://{p.netloc}"

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
        })
        self.robots = Robots(self.session, self.base)
        cd = self.robots.crawl_delay()
        self.delay = max(delay, cd or 0)
        if cd and cd > delay:
            print(f"robots.txt pede {cd:g}s entre pedidos; usando {self.delay:g}s.")

        self.pages: dict[str, dict] = {}       # url -> dados da página
        self.alias: dict[str, str] = {}        # url pedida -> url final (redirecionamentos)
        self.links: dict[str, list[str]] = {}  # url -> links internos encontrados
        self.queue: deque[tuple[str, int]] = deque([(self.start, 0)])
        self.queued: set[str] = {self.start}
        self.blocked: set[str] = set()
        self._last_request = 0.0
        if use_sitemap:
            self._seed_sitemap()

    # ---- utilidades
    def same_site(self, url: str) -> bool:
        return site_key(urlparse(url).netloc) == self.site

    def _wait(self):
        pause = self.delay - (time.monotonic() - self._last_request)
        if pause > 0:
            time.sleep(pause)
        self._last_request = time.monotonic()

    def _get(self, url: str, stream: bool = True):
        """GET educado: espera o intervalo e recua em 429/503 (até 2 novas tentativas)."""
        for attempt in range(3):
            self._wait()
            t0 = time.monotonic()
            r = self.session.get(url, timeout=15, allow_redirects=True, stream=stream)
            r.elapsed_ms = round((time.monotonic() - t0) * 1000)
            if r.status_code not in (429, 503) or attempt == 2:
                return r
            retry = r.headers.get("Retry-After", "")
            wait = min(float(retry), 60) if retry.isdigit() else 5 * (attempt + 1)
            print(f"   servidor pediu calma ({r.status_code}); esperando {wait:g}s")
            r.close()
            time.sleep(wait)
        return r

    def _seed_sitemap(self):
        sources = self.robots.sitemaps or [f"{self.base}/sitemap.xml"]
        added = 0
        for sm in sources[:3]:
            try:
                r = self._get(sm, stream=False)
                if r.status_code != 200:
                    continue
                for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)[:500]:
                    u = normalize(loc, self.keep_query)
                    if u and self.same_site(u) and u not in self.queued and not SKIP_EXT.search(urlparse(u).path):
                        self.queue.append((u, 1))
                        self.queued.add(u)
                        added += 1
            except requests.RequestException:
                continue
        if added:
            print(f"sitemap: {added} endereços adicionados à fila")

    # ---- uma página
    def fetch(self, url: str, depth: int) -> dict:
        page = {"url": url, "depth": depth, "status": None, "title": "", "description": "",
                "h1": "", "lang": "", "canonical": "", "noindex": False, "words": 0,
                "response_ms": None, "size_kb": None, "links_internal": 0,
                "links_external": 0, "images_no_alt": 0, "content_type": "", "error": ""}
        try:
            r = self._get(url)
        except requests.RequestException as exc:
            page["error"] = type(exc).__name__
            return page
        with r:
            page["status"] = r.status_code
            page["response_ms"] = r.elapsed_ms
            page["content_type"] = r.headers.get("Content-Type", "").split(";")[0].strip()
            final = normalize(r.url, self.keep_query)
            if final and final != url:
                page["redirected_to"] = final
                if not self.same_site(final):
                    page["error"] = "redireciona para outro site"
                    return page
            if r.status_code >= 400:
                page["error"] = f"HTTP {r.status_code}"
                return page
            if "html" not in page["content_type"]:
                page["error"] = "não é HTML"
                return page
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    page["error"] = "página muito grande (cortada)"
                    break
            page["size_kb"] = round(len(body) / 1024, 1)
            encoding = r.encoding if "charset" in r.headers.get("Content-Type", "").lower() else None

        soup = BeautifulSoup(body, PARSER, from_encoding=encoding)
        here = page.get("redirected_to", url)
        page["title"] = soup.title.get_text(" ", strip=True)[:160] if soup.title else ""
        meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        page["description"] = (meta.get("content") or "").strip()[:300] if meta else ""
        robots_meta = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
        page["noindex"] = bool(robots_meta and "noindex" in (robots_meta.get("content") or "").lower())
        h1 = soup.find("h1")
        page["h1"] = h1.get_text(" ", strip=True)[:160] if h1 else ""
        page["lang"] = (soup.html.get("lang") or "") if soup.html else ""
        canon = soup.find("link", rel=lambda v: v and "canonical" in v)
        page["canonical"] = urljoin(here, canon["href"]) if canon and canon.get("href") else ""
        page["images_no_alt"] = sum(1 for img in soup.find_all("img") if not (img.get("alt") or "").strip())

        base_tag = soup.find("base", href=True)
        base_url = urljoin(here, base_tag["href"]) if base_tag else here
        internal: list[str] = []
        seen_here: set[str] = set()
        external = 0
        nofollow_page = bool(robots_meta and "nofollow" in (robots_meta.get("content") or "").lower())
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
                continue
            target = normalize(urljoin(base_url, href), self.keep_query)
            if not target:
                continue
            if not self.same_site(target):
                external += 1
                continue
            if target in seen_here or target == here:
                continue
            seen_here.add(target)
            internal.append(target)
        page["links_internal"] = len(internal)
        page["links_external"] = external

        for tag in soup(["script", "style", "noscript", "template", "svg"]):
            tag.decompose()
        page["words"] = len(soup.get_text(" ", strip=True).split())

        if not nofollow_page:
            self.links[here] = internal[: self.links_per_page]
        return page

    # ---- laço principal
    def run(self):
        visited = 0
        print(f"\nRastreando {self.start}  (até {self.max_pages} páginas, profundidade {self.max_depth}, "
              f"{self.delay:g}s entre pedidos)\n")
        try:
            while self.queue and visited < self.max_pages:
                url, depth = self.queue.popleft()
                if url in self.pages or url in self.alias:
                    continue
                if not self.robots.can_fetch(url):
                    self.blocked.add(url)
                    continue
                if SKIP_EXT.search(urlparse(url).path):
                    continue
                page = self.fetch(url, depth)
                final = page.get("redirected_to")
                if final and final != url:
                    self.alias[url] = final
                    if final in self.pages:  # já tínhamos essa página
                        continue
                    page["url"] = final
                    page["requested_url"] = url
                key = page["url"]
                self.pages[key] = page
                visited += 1
                mark = "OK " if not page["error"] else "!! "
                label = page["title"] or page["error"] or key
                ms = f"{page['response_ms']}ms" if page["response_ms"] is not None else "-"
                print(f"[{visited:>3}/{self.max_pages}] {mark}{page['status'] or '---'} {ms:>7}  "
                      f"prof.{depth}  {label[:60]}")
                if depth < self.max_depth:
                    for target in self.links.get(key, []):
                        if target not in self.queued:
                            self.queued.add(target)
                            self.queue.append((target, depth + 1))
        except KeyboardInterrupt:
            print("\nInterrompido. Salvando o que já foi coletado...")
        return self.build()

    # ---- monta o mapa
    def build(self) -> dict:
        resolve = lambda u: self.alias.get(u, u)
        ids = {url: str(i) for i, url in enumerate(self.pages)}
        edges, inbound, broken = [], {u: 0 for u in self.pages}, []
        for src, targets in self.links.items():
            if src not in ids:
                continue
            for t in targets:
                t = resolve(t)
                if t in ids and t != src:
                    edges.append({"source": ids[src], "target": ids[t]})
                    inbound[t] += 1
                    st = self.pages[t]["status"]
                    if st is None or st >= 400:
                        broken.append({"from": src, "to": t, "status": st})
        # remove arestas repetidas mantendo a ordem
        uniq = list({(e["source"], e["target"]): e for e in edges}.values())
        nodes = []
        for url, p in self.pages.items():
            n = {"id": ids[url], "title": p["title"] or p["h1"] or urlparse(url).path or self.site,
                 **{k: v for k, v in p.items() if k != "title"}, "page_title": p["title"],
                 "links_in": inbound[url]}
            nodes.append(n)

        times = [p["response_ms"] for p in self.pages.values() if p["response_ms"] is not None]
        ok = [p for p in self.pages.values() if p["status"] and p["status"] < 400 and not p["error"]]
        stats = {
            "pages": len(nodes), "edges": len(uniq), "ok": len(ok),
            "errors": sum(1 for p in self.pages.values() if p["error"]),
            "blocked_by_robots": len(self.blocked),
            "avg_response_ms": round(sum(times) / len(times)) if times else None,
            "missing_title": sum(1 for p in ok if not p["title"]),
            "missing_description": sum(1 for p in ok if not p["description"]),
            "broken_links": len(broken),
            "queue_left": len(self.queue),
        }
        return {"site": self.start, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "crawler": f"AranhaDigital {VERSION}",
                "settings": {"max_pages": self.max_pages, "max_depth": self.max_depth, "delay": self.delay,
                             "keep_query": self.keep_query},
                "stats": stats, "nodes": nodes, "edges": uniq, "broken_links": broken[:500],
                "blocked": sorted(self.blocked)[:200]}


# ----------------------------------------------------------------------------- saída
CSV_COLS = ["url", "status", "depth", "page_title", "h1", "description", "words", "response_ms",
            "size_kb", "links_in", "links_internal", "links_external", "images_no_alt",
            "lang", "canonical", "noindex", "requested_url", "error"]


def save(result: dict, json_path: str, csv_path: str):
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:  # -sig: acentos certos no Excel
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore", delimiter=";")
        w.writeheader()
        for n in result["nodes"]:
            w.writerow({c: n.get(c, "") for c in CSV_COLS})


def summary(result: dict):
    s, nodes = result["stats"], result["nodes"]
    print("\n" + "=" * 64)
    print(f" {s['pages']} páginas · {s['edges']} conexões · {s['errors']} com erro · "
          f"{s['blocked_by_robots']} bloqueadas pelo robots.txt")
    if s["avg_response_ms"] is not None:
        print(f" tempo médio de resposta: {s['avg_response_ms']} ms")
    print(f" sem título: {s['missing_title']} · sem descrição: {s['missing_description']} · "
          f"links quebrados: {s['broken_links']}")
    top = sorted(nodes, key=lambda n: n["links_in"], reverse=True)[:5]
    if top and top[0]["links_in"]:
        print("\n Páginas mais linkadas:")
        for n in top:
            print(f"   {n['links_in']:>3} ← {n['title'][:55]}")
    slow = sorted((n for n in nodes if n["response_ms"]), key=lambda n: n["response_ms"], reverse=True)[:3]
    if slow:
        print("\n Mais lentas:")
        for n in slow:
            print(f"   {n['response_ms']:>5} ms  {n['url'][:60]}")
    if s["queue_left"]:
        print(f"\n Ainda havia {s['queue_left']} endereços na fila. Aumente --max-pages para ir mais longe.")
    print("=" * 64)


def ask(prompt: str, default):
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    try:
        return type(default)(raw)
    except ValueError:
        return default


def main():
    ap = argparse.ArgumentParser(description="Aranha Digital: mapeia páginas públicas de um site.")
    ap.add_argument("url", nargs="?", help="endereço inicial, ex.: https://exemplo.com")
    ap.add_argument("-p", "--max-pages", type=int, default=40, help="máximo de páginas (padrão 40)")
    ap.add_argument("-d", "--max-depth", type=int, default=3, help="cliques a partir da inicial (padrão 3)")
    ap.add_argument("--delay", type=float, default=1.5, help="segundos entre pedidos (mínimo 0.5)")
    ap.add_argument("--links", type=int, default=40, help="links seguidos por página (padrão 40)")
    ap.add_argument("--keep-query", action="store_true", help="trata ?parametros como páginas diferentes")
    ap.add_argument("--sitemap", action="store_true", help="também usa o sitemap.xml para achar páginas")
    ap.add_argument("-o", "--out", default="mapa.json", help="arquivo JSON de saída")
    ap.add_argument("--csv", default="relatorio.csv", help="arquivo CSV de saída")
    a = ap.parse_args()

    if not a.url:  # modo interativo (Pydroid / duplo clique)
        print(f"ARANHA DIGITAL {VERSION}\n")
        a.url = input("Endereço do site (https://...): ").strip()
        if a.url and "://" not in a.url:
            a.url = "https://" + a.url
        a.max_pages = ask("Quantas páginas no máximo", a.max_pages)
        a.max_depth = ask("Profundidade máxima", a.max_depth)
        a.sitemap = ask("Usar sitemap.xml? (s/n)", "n").lower().startswith("s")

    a.max_pages = max(1, min(a.max_pages, 2000))
    a.delay = max(0.5, a.delay)
    try:
        crawler = Crawler(a.url, a.max_pages, a.max_depth, a.delay, a.links, a.keep_query, a.sitemap)
        if crawler.robots.deny_all:
            sys.exit("O robots.txt deste site nega acesso a robôs. Nada foi coletado.")
        if not crawler.robots.can_fetch(crawler.start):
            sys.exit("O robots.txt não permite rastrear a página inicial. Nada foi coletado.")
        result = crawler.run()
    except (ValueError, RuntimeError) as exc:
        sys.exit(f"Erro: {exc}")
    save(result, a.out, a.csv)
    summary(result)
    print(f"\nSalvo: {a.out} (abra no aranha.html) e {a.csv} (planilha)")


if __name__ == "__main__":
    main()
