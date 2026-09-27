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

import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
import re
import gc  # Adicionado para limpeza agressiva de RAM
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Importação lazy de dependências opcionais
# ---------------------------------------------------------------------------

_requests_cached:    object | None = None
_http_adapter_cached: object | None = None
_retry_cached:        object | None = None
_bs4_cached:          object | None = None
_requests_loaded      = False
_bs4_loaded           = False


def _get_requests():
    global _requests_cached, _http_adapter_cached, _retry_cached, _requests_loaded
    if not _requests_loaded:
        _requests_loaded = True
        try:
            import requests as _req
            from requests.adapters import HTTPAdapter as _HA
            from urllib3.util.retry import Retry as _Rt
            _requests_cached, _http_adapter_cached, _retry_cached = _req, _HA, _Rt
        except ImportError:
            pass
    return _requests_cached, _http_adapter_cached, _retry_cached


def _get_bs4():
    global _bs4_cached, _bs4_loaded
    if not _bs4_loaded:
        _bs4_loaded = True
        try:
            from bs4 import BeautifulSoup as _BS4
            _bs4_cached = _BS4
        except ImportError:
            pass
    return _bs4_cached


def _get_local_index():
    try:
        from engine.tools.local_index import search_local, index_info
        return search_local, index_info
    except ImportError:
        return None, None


# ---------------------------------------------------------------------------
# Resultado de busca
# ---------------------------------------------------------------------------

@dataclass
class CrawlerResult:
    source:  str
    query:   str
    title:   str = ""
    url:     str = ""
    context: str = ""
    error:   Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.context.strip())

    def to_prompt_block(self, max_chars: int = 2000) -> str:
        if not self.ok:
            return ""
        return (
            f"[CTX-BEGIN]\n"
            f"scope: {self.source} | {self.title}\n"
            f"url: {self.url}\n"
            f"{self.context[:max_chars]}\n"
            f"[CTX-END]\n"
        )


# ---------------------------------------------------------------------------
# Sessão HTTP resiliente
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
# EthicalScraper — robots.txt
# ---------------------------------------------------------------------------

class _EthicalScraper:
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
            return True


_session_cache: dict[str, CrawlerResult] = {}
CTX_MAX_CHARS: int = 400


# ---------------------------------------------------------------------------
# Fontes de Busca
# ---------------------------------------------------------------------------

def _clean_wiki_html(html: str) -> str:
    BS4 = _get_bs4()
    if BS4 is None:
        return re.sub(r'<[^>]+>', ' ', html).strip()
    
    # Proteção de RAM
    html_content = html[:100000]
    soup = BS4(html_content, "html.parser")
    for unwanted in soup.find_all(["table", "style", "script", "sup"]):
        unwanted.decompose()
    text = soup.get_text(separator=" ", strip=True)
    
    del soup
    del html_content
    gc.collect()
    return text


def search_wikipedia(query: str, lang: str = "pt", session=None, max_chars: int = 2000) -> CrawlerResult:
    cache_key = f"wiki:{lang}:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("wikipedia", query, error="requests nao instalado")

    sess = session or _make_session()
    base = query.replace(" ", "_")
    slug_variants = list(dict.fromkeys([
        base[0].upper() + base[1:],
        base.title().replace(" ", "_"),
        base,
        base.split("_")[0][0].upper() + base.split("_")[0][1:],
        base.upper(),
    ]))

    tried = []
    for try_lang in ([lang, "en"] if lang != "en" else ["en", "pt"]):
        for slug in slug_variants:
            url = f"https://{try_lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(slug)}"
            tried.append(url)
            try:
                r = sess.get(url, timeout=10)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                data = r.json()
                extract = data.get("extract", "")
                if not extract:
                    continue
                result = CrawlerResult(
                    source  = f"wikipedia-{try_lang}",
                    query   = query,
                    title   = data.get("title", query),
                    url     = data.get("content_urls", {}).get("desktop", {}).get("page", url),
                    context = extract[:max_chars],
                )
                _session_cache[cache_key] = result
                return result
            except Exception:
                continue

    return CrawlerResult("wikipedia", query, error=f"Nao encontrado: {query!r} (tentou {len(tried)} slugs)")


def search_stackoverflow(query: str, site: str = "stackoverflow", session=None, max_results: int = 1, max_chars: int = 2000) -> CrawlerResult:
    cache_key = f"so:{site}:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("stackoverflow", query, error="requests nao instalado")

    sess = session or _make_session()
    try:
        r = sess.get(
            "https://api.stackexchange.com/2.3/search/advanced",
            params={"order": "desc", "sort": "relevance", "q": query, "site": site, "filter": "withbody", "pagesize": max_results},
            timeout=10,
        )
        r.raise_for_status()
        data  = r.json()

        items = data.get("items", [])
        if not items:
            return CrawlerResult("stackoverflow", query, error=f"Nenhum resultado SO para: {query!r}")

        q_item  = items[0]
        q_id    = q_item.get("question_id")
        q_body  = q_item.get("body", "") or q_item.get("excerpt", "")

        if len(q_body.strip()) > 100:
            context_html = q_body
        else:
            context_html = q_body
            try:
                r2 = sess.get(
                    f"https://api.stackexchange.com/2.3/questions/{q_id}/answers",
                    params={"order": "desc", "sort": "votes", "site": site, "filter": "withbody", "pagesize": 1},
                    timeout=10,
                )
                r2.raise_for_status()
                answers = r2.json().get("items", [])
                if answers:
                    context_html = answers[0].get("body", "") or context_html
            except Exception:
                pass

        # Proteção de RAM: limita a string e deleta referências ao DOM
        BS4 = _get_bs4()
        if BS4 and context_html:
            html_content = context_html[:100000]
            soup = BS4(html_content, "html.parser")
            body_text = soup.get_text(separator=" ", strip=True)
            del soup
            del html_content
            gc.collect()
        elif context_html:
            body_text = re.sub(r'<[^>]+>', ' ', context_html).strip()
        else:
            body_text = ""

        if not body_text.strip():
            return CrawlerResult("stackoverflow", query, error="Corpo vazio")
            
        result = CrawlerResult(
            source  = "stackoverflow",
            query   = query,
            title   = q_item.get("title", query),
            url     = q_item.get("link", ""),
            context = body_text[:max_chars],
        )
        _session_cache[cache_key] = result
        return result
    except Exception as e:
        return CrawlerResult("stackoverflow", query, error=str(e))


def search_arxiv(query: str, max_results: int = 1, session=None, max_chars: int = 2000) -> CrawlerResult:
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
            params={"search_query": f"all:{query}", "start": 0, "max_results": max_results},
            timeout=15,
        )
        r.raise_for_status()
        time.sleep(3)

        root = ET.fromstring(r.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return CrawlerResult("arxiv", query, error=f"Nenhum paper para: {query!r}")

        entry   = entries[0]
        title   = (entry.findtext("atom:title", "", ns) or "").strip()
        summary = (entry.findtext("atom:summary", "", ns) or "").strip()
        url     = ""
        for link in entry.findall("atom:link", ns):
            if link.get("type") == "text/html":
                url = link.get("href", "")

        result = CrawlerResult("arxiv", query, title, url, summary[:max_chars])
        _session_cache[cache_key] = result
        return result
    except Exception as e:
        return CrawlerResult("arxiv", query, error=str(e))


def search_pypi(package: str, session=None) -> CrawlerResult:
    cache_key = f"pypi:{package}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("pypi", package, error="requests não instalado")

    sess = session or _make_session()
    try:
        r = sess.get(f"https://pypi.org/pypi/{urllib.parse.quote(package)}/json", timeout=10)
        r.raise_for_status()
        data  = r.json()
        info  = data.get("info", {})
        desc  = info.get("summary", "")
        ver   = info.get("version", "")
        long_d = info.get("description", "")

        context = f"Pacote: {package} v{ver}\nResumo: {desc}\n"
        if long_d:
            clean = re.sub(r'#{1,6}\s+', '', long_d)
            clean = re.sub(r'\n{3,}', '\n\n', clean)
            context += clean[:1500]

        result = CrawlerResult("pypi", package, f"{package} v{ver}", f"https://pypi.org/project/{package}/", context[:2000])
        _session_cache[cache_key] = result
        return result
    except Exception as e:
        return CrawlerResult("pypi", package, error=str(e))


def search_github(query: str, token: str | None = None, session=None, max_results: int = 2) -> CrawlerResult:
    cache_key = f"github:{query}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("github", query, error="requests não instalado")

    sess = session or _make_session()
    if token:
        sess.headers.update({"Authorization": f"Bearer {token}"})
    sess.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})

    try:
        r = sess.get("https://api.github.com/search/repositories", params={"q": query, "sort": "stars", "order": "desc", "per_page": max_results}, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return CrawlerResult("github", query, error=f"Nenhum repo para: {query!r}")

        parts = []
        for repo in items[:max_results]:
            parts.append(f"Repositório: {repo.get('full_name', '')}\nDescrição: {repo.get('description', 'sem descrição')}\n"
                         f"Linguagem: {repo.get('language', '')}  Stars: {repo.get('stargazers_count', 0)}\nURL: {repo.get('html_url', '')}")
            time.sleep(0.2)

        result = CrawlerResult("github", query, items[0].get("full_name", query), items[0].get("html_url", ""), "\n\n".join(parts)[:2000])
        _session_cache[cache_key] = result
        return result
    except Exception as e:
        return CrawlerResult("github", query, error=str(e))


# ---------------------------------------------------------------------------
# Generic (Corrigido: Sintaxe Resolvida e RAM Protegida)
# ---------------------------------------------------------------------------

def search_generic(url: str, session=None, max_chars: int = 2000) -> CrawlerResult:
    cache_key = f"generic:{url}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    requests, _, _ = _get_requests()
    if requests is None:
        return CrawlerResult("generic", url, error="requests não instalado")

    ethical = _EthicalScraper()
    if not ethical.can_fetch(url):
        return CrawlerResult("generic", url, error=f"robots.txt proíbe acesso: {url}")

    sess = session or _make_session()
    try:
        r = sess.get(url, timeout=10)
        r.raise_for_status()

        # Proteção de RAM: Limita a página para evitar que o BS4 destrua a memória
        html_content = r.text[:150000]

        BS4 = _get_bs4()
        if BS4 is None:
            text = re.sub(r'<[^>]+>', ' ', html_content).strip()
            title = url
        else:
            soup  = BS4(html_content, "html.parser")
            title = soup.title.string.strip() if soup.title else url
            
            for tag in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "svg", "button", "noscript"]):
                tag.decompose()
                
            body = soup.find("main") or soup.find("article") or soup.find("body")
            if body:
                lines = [l.strip() for l in body.get_text(separator="\n", strip=True).split("\n") if len(l.strip()) > 40]
                text = "\n".join(lines)
            else:
                text = soup.get_text(separator="\n", strip=True)

            # Destrói a árvore DOM e força GC imediatamente
            del soup
            del html_content
            gc.collect()

        result = CrawlerResult("generic", url, title, url, text[:max_chars])
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        return CrawlerResult("generic", url, error=str(e))


# ---------------------------------------------------------------------------
# OrnCrawler
# ---------------------------------------------------------------------------

class OrnCrawler:
    _RATE_LIMITS: dict[str, float] = {
        "arxiv.org":             3.0,
        "api.stackexchange.com": 0.5,
        "api.github.com":        0.2,
        "wikipedia.org":         0.1,
        "pypi.org":              0.1,
    }
    _last_request: dict[str, float] = {}

    def __init__(self, github_token: str | None = None, verify_ssl: bool = True):
        self._session      = _make_session(verify_ssl=verify_ssl)
        self._ethical      = _EthicalScraper()
        self.github_token  = github_token
        self.verify_ssl    = verify_ssl
        self._context_limit = 2000

    @staticmethod
    def _is_code_query(query: str) -> bool:
        q = (query or "").lower()
        return ("." in q or any(kw in q for kw in ["python", "javascript", "typescript", "java", "c++", "c#", "ruby", "php", "erro", "error", "exception", "stack", "algoritmo", "algorithm", "quicksort", "funcao", "function", "class", "import", "async", "await", "api", "code"]))

    def _rank_local_source_ids(self, source_ids: list[str], query: str) -> list[str]:
        q = (query or "").lower()
        q_tokens = [t for t in re.findall(r"[a-z0-9_]+", q) if len(t) >= 3]
        is_code = self._is_code_query(query)

        def _score(src_id: str) -> tuple[int, int, str]:
            sid = src_id.lower()
            score = 0
            if is_code and any(k in sid for k in ["computer", "stackexchange", "softwareengineering", "program", "code", "python"]):
                score += 8
            if not is_code and any(k in sid for k in ["chem", "biolog", "hist", "geo"]):
                score += 4
            score += sum(1 for t in q_tokens if t in sid)
            return (-score, len(sid), sid)

        return sorted(source_ids, key=_score)

    def _rate_wait(self, domain: str) -> None:
        limit = self._RATE_LIMITS.get(domain, 0.0)
        if limit <= 0: return
        elapsed = time.time() - self._last_request.get(domain, 0)
        if elapsed < limit: time.sleep(limit - elapsed)
        self._last_request[domain] = time.time()

    @staticmethod
    def _cache_key(source: str, query: str, lang: str = "pt") -> str:
        if source == "wikipedia":     return f"wiki:{lang}:{query}"
        if source == "stackoverflow": return f"so:stackoverflow:{query}"
        if source == "pypi":          return f"pypi:{query}"
        if source == "arxiv":         return f"arxiv:{query}"
        if source == "github":        return f"github:{query}"
        return ""

    def _cached(self, source: str, query: str, lang: str = "pt") -> CrawlerResult | None:
        key = self._cache_key(source, query, lang)
        if not key: return None
        return _session_cache.get(key)

    def search(self, query: str, source: str = "auto", lang: str = "pt", code_only: bool = False) -> CrawlerResult:
        query = query.strip()
        if not query: return CrawlerResult("none", query, error="query vazia")

        deps = self.check_deps()
        if not deps["requests"]:
            return CrawlerResult("none", query, error="requests nao instalado. Execute: pip install requests beautifulsoup4")

        if source == "local" or source.endswith("-local"):
            search_local, _ = _get_local_index()
            if search_local is None: return CrawlerResult(source, query, error="local_index não disponível")
            
            target_src = source.replace("-local", "") if source != "local" else None
            from pathlib import Path
            index_dir = Path("data/index")
            
            if index_dir.exists():
                src_ids = [db_file.stem for db_file in sorted(index_dir.glob("*.db"))]
                ranked_ids = self._rank_local_source_ids(src_ids, query)
                for src_id in ranked_ids:
                    if target_src and target_src not in src_id: continue
                    results = search_local(query, source_id=src_id, limit=1, code_only=code_only)
                    if results and results[0].ok:
                        ctx = results[0].to_prompt_block(max_chars=CTX_MAX_CHARS)
                        return CrawlerResult(f"{src_id}-local", query, results[0].title, "", ctx)
            
            return CrawlerResult(source, query, error=f"nada no índice local: {query!r}")

        if source == "auto":          return self._auto_search(query, lang, code_only=code_only)
        if source == "wikipedia":     
            c = self._cached("wikipedia", query, lang)
            if c: return c
            self._rate_wait("wikipedia.org"); return search_wikipedia(query, lang=lang, session=self._session, max_chars=self._context_limit)
        if source == "stackoverflow": 
            c = self._cached("stackoverflow", query, lang)
            if c: return c
            self._rate_wait("api.stackexchange.com"); return search_stackoverflow(query, session=self._session, max_chars=self._context_limit)
        if source == "pypi":          
            c = self._cached("pypi", query, lang)
            if c: return c
            self._rate_wait("pypi.org"); return search_pypi(query, session=self._session)
        if source == "arxiv":         
            c = self._cached("arxiv", query, lang)
            if c: return c
            self._rate_wait("arxiv.org"); return search_arxiv(query, session=self._session, max_chars=self._context_limit)
        if source == "github":        
            c = self._cached("github", query, lang)
            if c: return c
            self._rate_wait("api.github.com"); return search_github(query, token=self.github_token, session=self._session)
        if source.startswith("generic:"):
            return search_generic(source.split("generic:", 1)[1], session=self._session, max_chars=self._context_limit)

        return CrawlerResult(source, query, error=f"fonte desconhecida: {source!r}")

    def _auto_search(self, query: str, lang: str, code_only: bool = False) -> CrawlerResult:
        q = query.lower()

        search_local, _ = _get_local_index()
        if search_local is not None:
            from pathlib import Path
            index_dir = Path("data/index")
            if index_dir.exists():
                src_ids = [db_file.stem for db_file in sorted(index_dir.glob("*.db"))]
                for src_id in self._rank_local_source_ids(src_ids, query):
                    results = search_local(query, source_id=src_id, limit=1, code_only=code_only)
                    if results and results[0].ok:
                        ctx = results[0].to_prompt_block(max_chars=CTX_MAX_CHARS)
                        cached = CrawlerResult(f"{src_id}-local", query, results[0].title, "", ctx)
                        _session_cache[f"local:{src_id}:{query}"] = cached
                        return cached

        for src in ("wikipedia", "stackoverflow", "pypi", "arxiv", "github"):
            cached = self._cached(src, query, lang)
            if cached is not None and cached.ok: return cached

        is_single = len(query.split()) == 1
        is_lib = any(kw in q for kw in ["lib", "library", "package", "pip", "pypi", "module", "modulo"])
        if is_single or is_lib:
            result = search_pypi(query.split()[0], session=self._session)
            if result is not None and result.ok: return result

        is_code = ("." in query or any(kw in q for kw in ["como", "how", "erro", "error", "exception", "python", "funcao", "function", "async", "await", "class", "import", "list", "dict", "loop", "thread", "c++", "batch", "script"]))
        if is_code:
            self._rate_wait("api.stackexchange.com")
            result = search_stackoverflow(query, session=self._session, max_chars=self._context_limit)
            if result is not None and result.ok: return result

        if any(kw in q for kw in ["github", "repo", "open source", "framework", "tool"]):
            self._rate_wait("api.github.com")
            result = search_github(query, token=self.github_token, session=self._session)
            if result is not None and result.ok: return result

        if any(kw in q for kw in ["paper", "research", "neural", "algorithm", "transformer", "machine learning", "deep learning", "llm", "model"]):
            self._rate_wait("arxiv.org")
            result = search_arxiv(query, session=self._session, max_chars=self._context_limit)
            if result is not None and result.ok: return result

        self._rate_wait("wikipedia.org")
        result = search_wikipedia(query, lang=lang, session=self._session)
        if result is not None and result.ok: return result

        if not is_code:
            self._rate_wait("api.stackexchange.com")
            result = search_stackoverflow(query, session=self._session, max_chars=self._context_limit)
            if result is not None and result.ok: return result

        return CrawlerResult("auto", query, error=f"Todas as fontes falharam para: {query!r}.")

    def clear_cache(self) -> None:
        _session_cache.clear()

    def check_deps(self) -> dict[str, bool]:
        requests, _, _  = _get_requests()
        BS4             = _get_bs4()
        search_local, _ = _get_local_index()
        
        local_indexes = {}
        if search_local:
            from pathlib import Path
            idx_dir = Path("data/index")
            if idx_dir.exists():
                for db in idx_dir.glob("*.db"):
                    local_indexes[db.stem] = True
                    
        return {
            "requests":           requests is not None,
            "beautifulsoup4":     BS4 is not None,
            "local_index":        search_local is not None,
            "local_indexes":      local_indexes,
            "urllib.robotparser": True,
        }