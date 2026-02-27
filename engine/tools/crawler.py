# -*- coding: utf-8 -*-
"""
ORN — OrnCrawler (Hermes-Web)
Motor de busca autônoma para injeção de contexto no modelo.

Reciclado de: OLINE v3.6 (BaseCollector, EthicalScraper, wikipedia_io, 
              wikipedia_utils, stackexchange, arxiv)
Descartado:   Flask, SQLite, TF-IDF, NLTK, translator (desnecessários)

Fontes suportadas:
  wikipedia   — API REST /summary (sem scraping)
  stackexchange — API pública, CC BY-SA, 10k req/dia
  arxiv       — API XML pública, sem auth
  pypi        — API JSON pública, documentação de libs
  github      — API REST, token opcional, rate limit respeitado
  generic     — requests + robots.txt + BeautifulSoup (fallback)

Integração com orn think:
  orn think "pergunta" --search "termo"
  → CrawlerResult.context injetado como prefixo no prompt

Protocolo ético (OSL-19 / OLINE PASC 1.3):
  - robots.txt verificado antes de qualquer request genérico
  - User-Agent identificado: ORN-Crawler/1.0
  - Rate limit por domínio (configurável)
  - Timeout estrito: 10s por request
  - Cache em memória: evita re-busca na mesma sessão

God: Hermes — mensageiro, veloz e ético.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
import re

# Importação lazy de dependências opcionais
def _get_requests():
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        return requests, HTTPAdapter, Retry
    except ImportError:
        return None, None, None

def _get_bs4():
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Resultado de busca
# ---------------------------------------------------------------------------

@dataclass
class CrawlerResult:
    """Resultado unificado de qualquer fonte."""
    source:  str               # "wikipedia", "stackoverflow", etc.
    query:   str               # termo buscado
    title:   str = ""
    url:     str = ""
    context: str = ""          # texto limpo, pronto para injeção no prompt
    error:   Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.context.strip())

    def to_prompt_block(self, max_chars: int = 2000) -> str:
        """Formata para injeção no prompt do modelo."""
        if not self.ok:
            return ""
        header = f"[CONTEXTO — {self.source.upper()}] {self.title}\nFonte: {self.url}\n\n"
        body   = self.context[:max_chars]
        return header + body + "\n"


# ---------------------------------------------------------------------------
# Sessão HTTP resiliente (reciclado de OLINE BaseCollector v1.1)
# ---------------------------------------------------------------------------

def _make_session(user_agent: str = "ORN-Crawler/1.0 (local, ethical, non-commercial)",
                  verify_ssl: bool = True):
    requests, HTTPAdapter, Retry = _get_requests()
    if requests is None:
        return None
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://",  HTTPAdapter(max_retries=retries))
    s.headers.update({
        "User-Agent": user_agent,
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    })
    if not verify_ssl:
        s.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return s


# ---------------------------------------------------------------------------
# EthicalScraper — robots.txt (reciclado de OLINE generic_utils v1.2)
# ---------------------------------------------------------------------------

class _EthicalScraper:
    """Verifica robots.txt antes de qualquer scraping genérico."""

    def __init__(self, user_agent: str = "ORN-Crawler/1.0"):
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.user_agent = user_agent

    def can_fetch(self, url: str) -> bool:
        try:
            parsed = urllib.parse.urlparse(url)
            if not parsed.netloc:
                return True
            domain = f"{parsed.scheme}://{parsed.netloc}"
            if domain not in self._cache:
                rp = urllib.robotparser.RobotFileParser()
                rp.set_url(f"{domain}/robots.txt")
                rp.read()
                self._cache[domain] = rp
            return self._cache[domain].can_fetch(self.user_agent, url)
        except Exception:
            return True   # dúvida = permite (fail-open para APIs públicas)


# ---------------------------------------------------------------------------
# Cache de sessão (evita re-busca dentro da mesma sessão Python)
# ---------------------------------------------------------------------------

_session_cache: dict[str, CrawlerResult] = {}


# ---------------------------------------------------------------------------
# Wikipedia — API REST /summary (sem scraping, sem robots issues)
# ---------------------------------------------------------------------------

def _clean_wiki_html(html: str) -> str:
    """Reciclado de OLINE wikipedia_utils v1.0 — remove navboxes, tabelas."""
    BS4 = _get_bs4()
    if BS4 is None:
        # Fallback: remove tags HTML manualmente
        return re.sub(r'<[^>]+>', ' ', html).strip()
    soup = BS4(html, "html.parser")
    for unwanted in soup.find_all(["table", "style", "script", "sup"]):
        unwanted.decompose()
    return soup.get_text(separator=" ", strip=True)


def search_wikipedia(query: str, lang: str = "pt",
                     session=None, max_chars: int = 2000) -> CrawlerResult:
    """
    Wikipedia REST API /summary — retorna resumo limpo.
    API oficial, sem scraping, sem robots.txt.
    Tenta PT primeiro, fallback EN. Case-insensitive via slug variants.
    """
    cache_key = f"wiki:{lang}:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("wikipedia", query,
                             error="requests nao instalado")

    sess = session or _make_session()

    # Wikipedia REST API e case-sensitive — testa variantes de capitalização
    base = query.replace(" ", "_")
    slug_variants = list(dict.fromkeys([
        base[0].upper() + base[1:],                    # Asyncio_python
        base.title().replace(" ", "_"),                 # Asyncio_Python
        base,                                           # asyncio_python
        base.split("_")[0][0].upper() +                # Asyncio (só 1o termo)
            base.split("_")[0][1:],
        base.upper(),                                   # ASYNCIO (raro mas existe)
    ]))

    tried = []
    for try_lang in ([lang, "en"] if lang != "en" else ["en", "pt"]):
        for slug in slug_variants:
            url = (f"https://{try_lang}.wikipedia.org"
                   f"/api/rest_v1/page/summary/{urllib.parse.quote(slug)}")
            tried.append(url)
            try:
                r = sess.get(url, timeout=10)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                # Detecta proxy retornando HTML em vez de JSON
                ct = r.headers.get("Content-Type", "")
                if "html" in ct.lower() or not r.text.strip():
                    sess2 = _make_session(verify_ssl=False)
                    r = sess2.get(url, timeout=10)
                    r.raise_for_status()
                try:
                    data = r.json()
                except Exception:
                    continue
                extract = data.get("extract", "")
                if not extract:
                    continue
                result = CrawlerResult(
                    source  = f"wikipedia-{try_lang}",
                    query   = query,
                    title   = data.get("title", query),
                    url     = data.get("content_urls", {})
                                  .get("desktop", {}).get("page", url),
                    context = extract[:max_chars],
                )
                _session_cache[cache_key] = result
                return result
            except Exception:
                continue

    return CrawlerResult("wikipedia", query,
                         error=f"Nao encontrado: {query!r} (tentou {len(tried)} slugs)")



def search_stackoverflow(query: str, site: str = "stackoverflow",
                         session=None, max_results: int = 2,
                         max_chars: int = 2000) -> CrawlerResult:
    """
    Stack Exchange API v2.3 — busca perguntas e retorna contexto util.
    Quota: 10.000 req/dia sem token. CC BY-SA 4.0.
    """
    cache_key = f"so:{site}:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("stackoverflow", query,
                             error="requests nao instalado")

    sess = session or _make_session()

    try:
        # Passo 1: busca perguntas com body incluido
        r = sess.get(
            "https://api.stackexchange.com/2.3/search/advanced",
            params={
                "order": "desc", "sort": "relevance",
                "q": query, "site": site,
                "filter": "withbody",   # garante body na pergunta
                "pagesize": max_results,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        quota = data.get("quota_remaining", "?")
        if isinstance(quota, int) and quota < 50:
            print(f"[CRAWLER] StackExchange quota baixa: {quota}")

        items = data.get("items", [])
        if not items:
            return CrawlerResult("stackoverflow", query,
                                 error=f"Nenhum resultado SO para: {query!r}")

        q_item  = items[0]
        q_id    = q_item.get("question_id")
        q_title = q_item.get("title", query)
        q_url   = q_item.get("link", "")
        q_body  = q_item.get("body", "")

        # Passo 2: busca respostas com body
        context_html = ""
        try:
            r2 = sess.get(
                f"https://api.stackexchange.com/2.3/questions/{q_id}/answers",
                params={
                    "order": "desc", "sort": "votes",
                    "site": site,
                    "filter": "withbody",   # garante body nas respostas
                    "pagesize": 1,
                },
                timeout=10,
            )
            r2.raise_for_status()
            answers = r2.json().get("items", [])
            if answers:
                context_html = answers[0].get("body", "")
        except Exception:
            pass

        # Usa body da pergunta se resposta estiver vazia
        if not context_html:
            context_html = q_body

        # Limpa HTML
        BS4 = _get_bs4()
        if BS4 and context_html:
            body_text = BS4(context_html, "html.parser").get_text(separator=" ", strip=True)
        elif context_html:
            body_text = re.sub(r'<[^>]+>', ' ', context_html).strip()
        else:
            body_text = ""

        # Fallback: usa titulo + snippet se body ainda vazio
        if not body_text.strip():
            snippet = q_item.get("excerpt", q_item.get("body_markdown", ""))
            body_text = snippet or q_title

        if not body_text.strip():
            return CrawlerResult("stackoverflow", query,
                                 error=f"SO retornou resposta vazia para: {query!r}")

        time.sleep(0.5)

        result = CrawlerResult(
            source  = f"stackoverflow-{site}",
            query   = query,
            title   = q_title,
            url     = q_url,
            context = body_text[:max_chars],
        )
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("stackoverflow", query, error=str(e))



def search_arxiv(query: str, max_results: int = 1,
                 session=None, max_chars: int = 2000) -> CrawlerResult:
    """
    ArXiv API pública — papers científicos.
    Rate limit: 1 req / 3s (respeitado). Sem auth.
    """
    cache_key = f"arxiv:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("arxiv", query, error="requests não instalado")

    sess = session or _make_session()
    try:
        r = sess.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
            },
            timeout=15,
        )
        r.raise_for_status()
        time.sleep(3)   # rate limit OLINE ArXiv

        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return CrawlerResult("arxiv", query,
                                 error=f"Nenhum paper para: {query!r}")

        entry   = entries[0]
        title   = (entry.findtext("atom:title", "", ns) or "").strip()
        summary = (entry.findtext("atom:summary", "", ns) or "").strip()
        url     = ""
        for link in entry.findall("atom:link", ns):
            if link.get("type") == "text/html":
                url = link.get("href", "")

        result = CrawlerResult(
            source  = "arxiv",
            query   = query,
            title   = title,
            url     = url,
            context = summary[:max_chars],
        )
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("arxiv", query, error=str(e))


# ---------------------------------------------------------------------------
# PyPI — API JSON (documentação de libs Python)
# ---------------------------------------------------------------------------

def search_pypi(package: str, session=None) -> CrawlerResult:
    """
    PyPI JSON API — metadados e descrição de pacotes Python.
    API pública, sem auth, sem rate limit documentado.
    """
    cache_key = f"pypi:{package}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("pypi", package, error="requests não instalado")

    sess = session or _make_session()
    try:
        r = sess.get(
            f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json",
            timeout=10,
        )
        r.raise_for_status()
        data  = r.json()
        info  = data.get("info", {})
        desc  = info.get("summary", "")
        home  = info.get("home_page", "") or info.get("project_url", "")
        ver   = info.get("version", "")
        long_d = info.get("description", "")

        context = f"Pacote: {package} v{ver}\nResumo: {desc}\n"
        if long_d:
            # Remove markdown excessivo da descrição longa
            clean = re.sub(r'#{1,6}\s+', '', long_d)
            clean = re.sub(r'\n{3,}', '\n\n', clean)
            context += clean[:1500]

        result = CrawlerResult(
            source  = "pypi",
            query   = package,
            title   = f"{package} v{ver}",
            url     = f"https://pypi.org/project/{package}/",
            context = context[:2000],
        )
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("pypi", package, error=str(e))


# ---------------------------------------------------------------------------
# GitHub — API REST (token opcional)
# ---------------------------------------------------------------------------

def search_github(query: str, token: str | None = None,
                  session=None, max_results: int = 2) -> CrawlerResult:
    """
    GitHub Search API — repositórios e código.
    Sem token: 10 req/min. Com token: 30 req/min.
    Respeita rate limit via header X-RateLimit-Remaining.
    """
    cache_key = f"github:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("github", query, error="requests não instalado")

    sess = session or _make_session()
    if token:
        sess.headers.update({"Authorization": f"Bearer {token}"})
    sess.headers.update({"Accept": "application/vnd.github+json",
                          "X-GitHub-Api-Version": "2022-11-28"})

    try:
        r = sess.get(
            "https://api.github.com/search/repositories",
            params={
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": max_results,
            },
            timeout=10,
        )
        # Rate limit
        remaining = int(r.headers.get("X-RateLimit-Remaining", 99))
        if remaining < 5:
            print(f"[CRAWLER] GitHub rate limit baixo: {remaining}")

        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return CrawlerResult("github", query,
                                 error=f"Nenhum repo para: {query!r}")

        parts = []
        for repo in items[:max_results]:
            name  = repo.get("full_name", "")
            desc  = repo.get("description", "sem descrição")
            stars = repo.get("stargazers_count", 0)
            lang  = repo.get("language", "")
            url   = repo.get("html_url", "")
            parts.append(
                f"Repositório: {name}\nDescrição: {desc}\n"
                f"Linguagem: {lang}  Stars: {stars}\nURL: {url}"
            )
            time.sleep(0.2)

        result = CrawlerResult(
            source  = "github",
            query   = query,
            title   = items[0].get("full_name", query),
            url     = items[0].get("html_url", ""),
            context = "\n\n".join(parts)[:2000],
        )
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("github", query, error=str(e))


# ---------------------------------------------------------------------------
# Generic — requests + robots.txt + BeautifulSoup (fallback)
# Reciclado de OLINE generic.py + generic_utils.py
# ---------------------------------------------------------------------------

def search_generic(url: str, session=None,
                   max_chars: int = 2000) -> CrawlerResult:
    """
    Scraping ético de URL arbitrária.
    Verifica robots.txt antes. Remove script/style/nav.
    Requer beautifulsoup4.
    """
    cache_key = f"generic:{url}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    BS4 = _get_bs4()
    if requests is None:
        return CrawlerResult("generic", url, error="requests não instalado")

    ethical = _EthicalScraper()
    if not ethical.can_fetch(url):
        return CrawlerResult("generic", url,
                             error=f"robots.txt proíbe acesso: {url}")

    sess = session or _make_session()
    try:
        r = sess.get(url, timeout=10)
        r.raise_for_status()

        if BS4 is None:
            text = re.sub(r'<[^>]+>', ' ', r.text).strip()
            title = url
        else:
            soup  = BS4(r.text, "html.parser")
            title = soup.title.string.strip() if soup.title else url
            # Limpeza UI agressiva (reciclado de OLINE clean_generic_html)
            for tag in soup.find_all(
                    ["script", "style", "nav", "header", "footer",
                     "aside", "form", "svg", "button", "noscript"]):
                tag.decompose()
            body = soup.find("main") or soup.find("article") or soup.find("body")
            if body:
                lines = [l.strip() for l in
                         body.get_text(separator="\n", strip=True).split("\n")
                         if len(l.strip()) > 40]
                text = "\n".join(lines)
            else:
                text = soup.get_text(separator="\n", strip=True)

        result = CrawlerResult(
            source  = "generic",
            query   = url,
            title   = title,
            url     = url,
            context = text[:max_chars],
        )
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("generic", url, error=str(e))


# ---------------------------------------------------------------------------
# OrnCrawler — interface unificada para o CLI/Executive
# ---------------------------------------------------------------------------

class OrnCrawler:
    """
    Interface principal do crawler para uso interno do ORN.
    
    Uso no CLI (engine/cli.py):
        crawler = OrnCrawler()
        result  = crawler.search("asyncio python", source="auto")
        prompt  = result.to_prompt_block() + user_prompt

    Uso programático:
        result = crawler.search("requests library", source="pypi")
        if result.ok:
            print(result.context)
    """

    # Fontes por prioridade para "auto"
    _AUTO_ORDER = ["wikipedia", "stackoverflow", "pypi", "arxiv", "github"]

    # Rate limits por domínio (segundos entre requests)
    _RATE_LIMITS: dict[str, float] = {
        "arxiv.org":          3.0,
        "api.stackexchange.com": 0.5,
        "api.github.com":     0.2,
        "wikipedia.org":      0.1,
        "pypi.org":           0.1,
    }
    _last_request: dict[str, float] = {}

    def __init__(self, github_token: str | None = None,
                 verify_ssl: bool = True):
        self._session      = _make_session(verify_ssl=verify_ssl)
        self._ethical      = _EthicalScraper()
        self.github_token  = github_token
        self.verify_ssl    = verify_ssl
        self._context_limit = 2000   # chars max injetados no prompt

    def _rate_wait(self, domain: str) -> None:
        """Respeita rate limit por domínio."""
        limit = self._RATE_LIMITS.get(domain, 0.0)
        if limit <= 0:
            return
        elapsed = time.time() - self._last_request.get(domain, 0)
        if elapsed < limit:
            time.sleep(limit - elapsed)
        self._last_request[domain] = time.time()

    def search(self, query: str, source: str = "auto",
               lang: str = "pt") -> CrawlerResult:
        """
        Ponto de entrada principal.

        source: "auto" | "wikipedia" | "stackoverflow" | "pypi" |
                "arxiv" | "github" | "generic:<url>"
        """
        query = query.strip()
        if not query:
            return CrawlerResult("none", query, error="query vazia")

        # Verifica dependencias na primeira chamada
        deps = self.check_deps()
        if not deps["requests"]:
            return CrawlerResult("none", query,
                error="requests nao instalado. Execute: pip install requests beautifulsoup4")

        if source == "auto":
            return self._auto_search(query, lang)

        if source == "wikipedia":
            self._rate_wait("wikipedia.org")
            return search_wikipedia(query, lang=lang,
                                    session=self._session,
                                    max_chars=self._context_limit)

        if source == "stackoverflow":
            self._rate_wait("api.stackexchange.com")
            return search_stackoverflow(query,
                                        session=self._session,
                                        max_chars=self._context_limit)

        if source == "pypi":
            self._rate_wait("pypi.org")
            return search_pypi(query, session=self._session)

        if source == "arxiv":
            self._rate_wait("arxiv.org")
            return search_arxiv(query, session=self._session,
                                max_chars=self._context_limit)

        if source == "github":
            self._rate_wait("api.github.com")
            return search_github(query, token=self.github_token,
                                 session=self._session)

        if source.startswith("generic:"):
            url = source.split("generic:", 1)[1]
            return search_generic(url, session=self._session,
                                  max_chars=self._context_limit)

        return CrawlerResult(source, query,
                             error=f"fonte desconhecida: {source!r}")
    def _auto_search(self, query: str, lang: str) -> CrawlerResult:
        """
        Estrategia auto: tenta fontes por prioridade ate encontrar resultado util.
        Heuristica de roteamento baseada na query.
        """
        q = query.lower()

        # PyPI first: query de palavra unica OU keyword de pacote
        is_single = len(query.split()) == 1
        is_lib = any(kw in q for kw in
                     ["lib", "library", "package", "pip", "pypi", "module", "modulo"])
        if is_single or is_lib:
            result = search_pypi(query.split()[0], session=self._session)
            if result.ok:
                return result

        # Stack Overflow: prioridade alta para queries de codigo
        is_code = (
            "." in query or
            any(kw in q for kw in [
                "como", "how", "erro", "error", "exception", "python",
                "funcao", "function", "async", "await", "class", "import",
                "list", "dict", "loop", "thread", "c++", "batch", "script",
            ])
        )
        if is_code:
            self._rate_wait("api.stackexchange.com")
            result = search_stackoverflow(query, session=self._session,
                                          max_chars=self._context_limit)
            if result.ok:
                return result

        # GitHub: repositorios
        if any(kw in q for kw in
               ["github", "repo", "open source", "framework", "tool"]):
            self._rate_wait("api.github.com")
            result = search_github(query, token=self.github_token,
                                   session=self._session)
            if result.ok:
                return result

        # ArXiv: papers
        if any(kw in q for kw in [
            "paper", "research", "neural", "algorithm", "transformer",
            "machine learning", "deep learning", "llm", "model",
        ]):
            self._rate_wait("arxiv.org")
            result = search_arxiv(query, session=self._session,
                                  max_chars=self._context_limit)
            if result.ok:
                return result

        # Wikipedia: fallback geral
        self._rate_wait("wikipedia.org")
        result = search_wikipedia(query, lang=lang, session=self._session)
        if result.ok:
            return result

        # Ultimo fallback: SO sem filtro de keywords
        if not is_code:
            self._rate_wait("api.stackexchange.com")
            result = search_stackoverflow(query, session=self._session,
                                          max_chars=self._context_limit)
            if result.ok:
                return result

        return CrawlerResult("auto", query,
                             error=f"Todas as fontes falharam para: {query!r}. "
                                   f"Tente: --search 'stackoverflow:query' ou 'wikipedia:query'")


    def clear_cache(self) -> None:
        """Limpa o cache de sessão."""
        _session_cache.clear()

    def check_deps(self) -> dict[str, bool]:
        """Verifica dependências disponíveis."""
        requests, _, _ = _get_requests()
        BS4 = _get_bs4()
        return {
            "requests":       requests is not None,
            "beautifulsoup4": BS4 is not None,
            "urllib.robotparser": True,   # stdlib
        }