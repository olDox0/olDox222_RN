from __future__ import annotations

# --- DOXOADE_VULCAN_BOOTSTRAP:START ---
from pathlib import Path as _doxo_path
import importlib.util as _doxo_importlib_util
import sys as _doxo_sys
import time as _doxo_time

_doxo_activate_vulcan = None
_doxo_install_meta_finder = None
_doxo_probe_embedded = None
_doxo_project_root = None
_doxo_boot_t0 = _doxo_time.monotonic()
_doxo_install_ms = 0
_doxo_embedded_ms = 0
_doxo_fallback_ms = 0

for _doxo_base in[_doxo_path(__file__).resolve(), *_doxo_path(__file__).resolve().parents]:
    _doxo_runtime_file = _doxo_base / ".doxoade" / "vulcan" / "runtime.py"
    if not _doxo_runtime_file.exists():
        continue
    _doxo_spec = _doxo_importlib_util.spec_from_file_location("_doxoade_vulcan_runtime", str(_doxo_runtime_file))
    if not (_doxo_spec and _doxo_spec.loader):
        continue
    _doxo_mod = _doxo_importlib_util.module_from_spec(_doxo_spec)
    _doxo_sys.modules["_doxoade_vulcan_runtime"] = _doxo_mod
    _doxo_spec.loader.exec_module(_doxo_mod)
    _doxo_activate_vulcan = getattr(_doxo_mod, "activate_vulcan", None)
    _doxo_install_meta_finder = getattr(_doxo_mod, "install_meta_finder", None)
    _doxo_probe_embedded = getattr(_doxo_mod, "probe_embedded", None)
    _doxo_project_root = str(_doxo_base)
    break

# 1. Instala MetaFinder primeiro
if callable(_doxo_install_meta_finder) and _doxo_project_root:
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_install_meta_finder(_doxo_project_root)
    except Exception:
        pass
    finally:
        _doxo_install_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 2. Tenta usar o loader "embedded"
try:
    _doxo_t = _doxo_time.monotonic()
    if _doxo_project_root:
        _embedded_path = _doxo_path(_doxo_project_root) / ".doxoade" / "vulcan" / "vulcan_embedded.py"
        if _embedded_path.exists():
            _doxo_spec2 = _doxo_importlib_util.spec_from_file_location("_doxoade_vulcan_embedded", str(_embedded_path))
            if _doxo_spec2 and _doxo_spec2.loader:
                _doxo_mod2 = _doxo_importlib_util.module_from_spec(_doxo_spec2)
                _doxo_sys.modules["_doxoade_vulcan_embedded"] = _doxo_mod2
                _doxo_spec2.loader.exec_module(_doxo_mod2)
                _doxo_activate_embedded = getattr(_doxo_mod2, "activate_embedded", None)
                _doxo_safe_call = getattr(_doxo_mod2, "safe_call", None)
                if callable(_doxo_activate_embedded):
                    try:
                        _doxo_activate_embedded(globals(), __file__, _doxo_project_root)
                    except Exception:
                        pass
                if callable(_doxo_safe_call):
                    try:
                        import sys as _d_sys
                        _bin_dir = _doxo_path(_doxo_project_root) / ".doxoade" / "vulcan" / "bin"
                        _vulcan_suffix = _d_sys.intern("_vulcan_optimized")
                        _suffix_len    = len(_vulcan_suffix)
                        for mname, mod in list(_d_sys.modules.items()):
                            try:
                                mfile = getattr(mod, "__file__", None)
                                if not mfile:
                                    continue
                                mpath = _doxo_path(mfile)
                                if _bin_dir not in mpath.parents:
                                    continue
                                for attr in dir(mod):
                                    if not attr.endswith(_vulcan_suffix):
                                        continue
                                    native_obj = getattr(mod, attr, None)
                                    if not callable(native_obj):
                                        continue
                                    base = attr[: -_suffix_len]
                                    try:
                                        setattr(mod, base, _doxo_safe_call(native_obj, getattr(mod, base, None)))
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                    except Exception:
                        pass
except Exception:
    pass
finally:
    _doxo_embedded_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 3. Fallback: runtime.activate_vulcan
if callable(_doxo_activate_vulcan):
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_activate_vulcan(globals(), __file__)
    except Exception:
        pass
    finally:
        _doxo_fallback_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 4. Diagnóstico opcional
if callable(_doxo_probe_embedded):
    try:
        __doxoade_vulcan_probe__ = _doxo_probe_embedded(_doxo_project_root)
        __doxoade_vulcan_probe__["install_meta_ms"] = _doxo_install_ms
        __doxoade_vulcan_probe__["embedded_load_ms"] = _doxo_embedded_ms
        __doxoade_vulcan_probe__["fallback_ms"] = _doxo_fallback_ms
        __doxoade_vulcan_probe__["boot_ms"] = int((_doxo_time.monotonic() - _doxo_boot_t0) * 1000)
        if _doxo_sys.environ.get("VULCAN_DIAG", "").strip() == "1":
            _doxo_sys.stderr.write(
                "[VULCAN:DIAG] "
                + "finder_count=" + str(__doxoade_vulcan_probe__.get("finder_count", 0)) + " "
                + "bin=" + str(__doxoade_vulcan_probe__.get("bin_count", 0)) + " "
                + "lib_bin=" + str(__doxoade_vulcan_probe__.get("lib_bin_count", 0)) + " "
                + "boot_ms=" + str(__doxoade_vulcan_probe__.get("boot_ms", 0)) + " "
                + "install_ms=" + str(__doxoade_vulcan_probe__.get("install_meta_ms", 0)) + " "
                + "embedded_ms=" + str(__doxoade_vulcan_probe__.get("embedded_load_ms", 0)) + " "
                + "fallback_ms=" + str(__doxoade_vulcan_probe__.get("fallback_ms", 0)) + "\n"
            )
    except Exception:
        pass
# --- DOXOADE_VULCAN_BOOTSTRAP:END ---

# -*- coding: utf-8 -*-
# engine/tools/local_index.py

import argparse
import array
import hashlib
import logging
import os
import re
import sqlite3
import struct
import sys
import time
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional

# dependências do projeto (mantidas)
from engine.tools.inverted_index import InvertedIndexBuilder, InvertedIndexSearcher
from engine.telemetry.core import orn_span, GLOBAL_TELEMETRY, record_direct_telemetry

# ---------------------------------------------------------------------------
# Config / constantes
# ---------------------------------------------------------------------------
logger = logging.getLogger("engine.tools.local_index")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ZIM_DIR = Path(os.environ.get("SICDOX_ZIM_DIR", "data/zim"))
INDEX_DIR = Path(os.environ.get("SICDOX_INDEX_DIR", "data/index"))

# Caminho padrão antigo mantido como fallback — preferir definir SICDOX_GGUF
_DEFAULT_GGUF = r"C:\Users\olDox222\Documents\A20251122\DOSSIER\Altonomo\Projetos_E_Programas\Projeto_OIA\olDox222RN\ORN\models\sicdox\Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF\qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
_GGUF_PATH_ENV = "SICDOX_GGUF"

# Regexes (consolidadas)
_RE_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_RE_NAV = re.compile(r'<[^>]*(navbox|mw-toc|mw-jump|sidebar|infobox|reflist)[^>]*>.*?</\w+>', re.DOTALL | re.IGNORECASE)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6});")
_RE_MULTI = re.compile(r"[ \t]{2,}")
_RE_NEWL = re.compile(r"\n{3,}")
_RE_URL = re.compile(r"https?://\S+")

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() not in ("0", "false", "no", "off")


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# HTML cleaning / helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str, max_chars: int = 8000) -> str:
    html = _RE_SCRIPT.sub(" ", html)
    html = _RE_NAV.sub(" ", html)
    html = _RE_TAG.sub(" ", html)
    html = _RE_ENTITY.sub(" ", html)
    html = _RE_URL.sub(" ", html)
    text = _RE_MULTI.sub(" ", html)
    text = _RE_NEWL.sub("\n\n", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Compression helpers (pyzstd optional)
# ---------------------------------------------------------------------------

def _compress(data: bytes) -> bytes:
    """
    Retorna blob com um byte de formato:
      b'\\x00' + raw_payload  -> não comprimido
      b'\\x01' + zstd_payload -> comprimido (pyzstd disponível)
    """
    try:
        import pyzstd
        compressed = pyzstd.compress(data)
        return b"\x01" + compressed
    except Exception:
        logger.debug("pyzstd unavailable; storing raw payload (flag 0)")
        return b"\x00" + data


def _decompress(data: bytes) -> bytes:
    """
    Interpreta o primeiro byte de flag e devolve os bytes payload (descomprimidos
    quando necessário). Não devolve dados comprimidos cru.
    """
    if not data:
        return data
    flag = data[0:1]
    payload = data[1:]
    if flag == b"\x00":
        return payload
    if flag == b"\x01":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            logger.exception("_decompress: pyzstd present at build but missing at runtime")
            # NÃO retornar payload comprimido — em vez disso sinalizamos erro
            raise RuntimeError("Unable to decompress zstd payload: pyzstd missing or decompression failed")
    # fallback: se não reconhecido, tentar heurística segura
    logger.warning("_decompress: unknown format flag %r; attempting to detect zstd magic", flag)
    if len(data) >= 5 and data[1:5] == b"\x28\xb5\x2f\xfd":
        try:
            import pyzstd
            return pyzstd.decompress(payload)
        except Exception:
            raise RuntimeError("Unknown blob format and pyzstd unavailable")
    # último recurso: devolver como-is (não ideal)
    return payload


# ---------------------------------------------------------------------------
# Read entry content (consolidated)
# ---------------------------------------------------------------------------

def _read_entry_content(entry) -> Optional[bytes]:
    for method in ("read", "get_data", "content", "data"):
        fn = getattr(entry, method, None)
        if fn is None:
            continue
        try:
            result = fn() if callable(fn) else fn
            if isinstance(result, (bytes, bytearray)) and len(result) > 0:
                return bytes(result)
            if isinstance(result, memoryview) and len(result) > 0:
                return bytes(result)
        except Exception:
            logger.debug("_read_entry_content: method %s failed", method, exc_info=True)
            continue

    for attr in ("_data", "_content", "raw"):
        val = getattr(entry, attr, None)
        if isinstance(val, (bytes, bytearray, memoryview)) and len(val) > 0:
            return bytes(val)
    return None


# ---------------------------------------------------------------------------
# TokenizerBridge (thread-safe, GGUF via env)
# ---------------------------------------------------------------------------

class TokenizerBridge:
    """Singleton leve que carrega apenas o vocab (vocab_only=True).
    Fornecer o caminho do GGUF via variável de ambiente SICDOX_GGUF é recomendado.
    """

    _llm_vocab = None
    _lock = Lock()

    @classmethod
    def get_gguf_path(cls) -> str:
        env = os.environ.get(_GGUF_PATH_ENV)
        if env and os.path.exists(env):
            return env
        if os.path.exists(_DEFAULT_GGUF):
            return _DEFAULT_GGUF
        raise FileNotFoundError(f"GGUF não encontrado. Defina { _GGUF_PATH_ENV } apontando para o arquivo .gguf")

    @classmethod
    def get_vocab(cls):
        if cls._llm_vocab is None:
            with cls._lock:
                if cls._llm_vocab is None:
                    try:
                        from llama_cpp import Llama
                    except Exception:
                        logger.exception("llama_cpp import falhou")
                        raise
                    gguf = cls.get_gguf_path()
                    logger.info("Carregando vocab_only do GGUF: %s", gguf)
                    cls._llm_vocab = Llama(model_path=gguf, vocab_only=True, verbose=False)
        return cls._llm_vocab

    @classmethod
    def text_to_bytes(cls, text: str) -> bytes:
        vocab = cls.get_vocab()
        tokens = vocab.tokenize(text.encode("utf-8"), add_bos=False)
        return array.array("i", tokens).tobytes()

    @classmethod
    def bytes_to_text(cls, data: bytes) -> str:
        # data expected to be token-array-bytes (length %4==0) after decompression.
        if not data:
            return ""
        if len(data) % 4 != 0:
            # Não tentar decodificar comprimido ou corrompido como UTF-8 sem avisar.
            logger.warning("bytes_to_text: data length %d not multiple of 4 — possible corrupted/compressed blob", len(data))
            try:
                # tentativa cuidadosa: devolve texto legível como fallback
                return data.decode("utf-8", errors="ignore")
            except Exception:
                return ""
        try:
            vocab = cls.get_vocab()
            arr = array.array("i")
            arr.frombytes(data)
            tokens = arr.tolist()
            if tokens and (max(tokens) >= vocab.n_vocab() or min(tokens) < 0):
                logger.warning("bytes_to_text: token ids outside vocab range; returning fallback decode")
                return data.decode("utf-8", errors="ignore")
            return vocab.detokenize(tokens).decode("utf-8", errors="ignore")
        except Exception:
            logger.exception("bytes_to_text failed; returning raw decode")
            return data.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# LocalResult (consolidado)
# ---------------------------------------------------------------------------

class LocalResult:
    __slots__ = ("source", "title", "body", "path")

    def __init__(self, source: str, title: str, body: str, path: str = ""):
        self.source = source
        self.title = title
        self.body = body
        self.path = path

    @property
    def ok(self) -> bool:
        return bool(self.title and self.body.strip())

    def get_snippet(self, query: str = "", max_chars: int = 600) -> str:
        if not self.ok:
            return ""
        text = self.body
        if query:
            q_lower = query.lower()
            t_lower = text.lower()
            idx = t_lower.find(q_lower)
            if idx == -1:
                for word in q_lower.split():
                    if len(word) > 3:
                        idx = t_lower.find(word)
                        if idx != -1:
                            break
            if idx != -1:
                start = max(0, idx - 80)
                end = min(len(text), start + max_chars)
                if start > 0:
                    space_idx = text.find(" ", start)
                    start = space_idx + 1 if space_idx != -1 else start
                snippet = text[start:end].strip()
                return f"...{snippet}..." if start > 0 else snippet
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def to_prompt_block(self, max_chars: int = 600, query: str = "") -> str:
        if not self.ok:
            return ""
        snippet = self.get_snippet(query, max_chars)
        return f"[CTX-BEGIN]\nscope: {self.source} | {self.title}\n{snippet}\n[CTX-END]\n"


# ---------------------------------------------------------------------------
# ZIM iteration
# ---------------------------------------------------------------------------

def _zim_to_source_id(zim_path: str | Path) -> str:
    name = Path(zim_path).stem
    name = name.replace("-", "_").replace(".", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return re.sub(r"_+", "_", name).strip("_").lower()


def _source_id_to_db(source_id: str) -> Path:
    return INDEX_DIR / f"{source_id}.db"


def _find_zim_for_source(source_id: str) -> Optional[Path]:
    if ZIM_DIR.exists():
        for zim in ZIM_DIR.glob("*.zim"):
            if _zim_to_source_id(zim) == source_id:
                return zim
    return None


def _iter_zim_entries(zim_path: str, verbose: bool = True) -> Iterator[tuple[str, str, str]]:
    import pyzim

    p = Path(zim_path).absolute()

    total_scanned = total_yielded = total_redirect = 0
    total_non_html = total_empty = total_error = 0

    with pyzim.Zim.open(str(p), mode="r") as zim:
        for entry in zim.iter_entries():
            total_scanned += 1

            if verbose and total_scanned % 5000 == 0:
                logger.info(
                    "[ZIM] scanned=%d yielded=%d redirect=%d non_html=%d empty=%d",
                    total_scanned,
                    total_yielded,
                    total_redirect,
                    total_non_html,
                    total_empty,
                )

            if getattr(entry, "is_redirect", False):
                total_redirect += 1
                continue

            ns = getattr(entry, "namespace", None)
            if ns is not None:
                if isinstance(ns, bytes):
                    ns = ns.decode("utf-8", errors="ignore")
                ns = str(ns).strip()
                if ns in ("I", "-", "X"):
                    total_non_html += 1
                    continue

            content_bytes = _read_entry_content(entry)
            if not content_bytes:
                total_empty += 1
                continue

            head = content_bytes[:400].lower()
            is_html = (
                b"<html" in head
                or b"<!doctype" in head
                or b"<body" in head
                or b"<p" in head
                or b"<div" in head
                or b"<h1" in head
                or b"<h2" in head
                or content_bytes[:1] == b"<"
            )
            if not is_html:
                total_non_html += 1
                continue

            try:
                title = getattr(entry, "title", "")
                if isinstance(title, bytes):
                    title = title.decode("utf-8", errors="ignore")
                title = str(title).strip()

                path = getattr(entry, "url", None) or getattr(entry, "path", "")
                if isinstance(path, bytes):
                    path = path.decode("utf-8", errors="ignore")
                path = str(path).strip()

                if not title:
                    title = path.split("/")[-1].replace("_", " ").strip()

                content = content_bytes.decode("utf-8", errors="replace")
                total_yielded += 1
                yield title, path, content

            except Exception:
                total_error += 1
                logger.debug("Error parsing zim entry", exc_info=True)
                continue

    if verbose:
        logger.info(
            "[ZIM] total: scanned=%d yielded=%d redirect=%d non_html=%d empty=%d error=%d",
            total_scanned,
            total_yielded,
            total_redirect,
            total_non_html,
            total_empty,
            total_error,
        )


# ---------------------------------------------------------------------------
# BUILD INDEX
# ---------------------------------------------------------------------------

def build_index(zim_path: str, source_id: Optional[str] = None, batch_size: int = 1000, verbose: bool = True) -> Path:
    try:
        import pyzim  # noqa: F401
    except ImportError:
        raise ImportError("pyzim não instalado. pip install pyzim")

    zim_path = str(zim_path)
    if not Path(zim_path).exists():
        raise FileNotFoundError(f"ZIM não encontrado: {zim_path}")

    # Garante que o vocab seja carregado no início (pode lançar FileNotFoundError)
    TokenizerBridge.get_vocab()

    if source_id is None:
        source_id = _zim_to_source_id(zim_path)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    db_path = str(_source_id_to_db(source_id))

    # --- Remover DB / índice existente para garantir rebuild limpo ---
    try:
        db_p = Path(db_path)
        inv_dir = INDEX_DIR / source_id
        if db_p.exists():
            logger.info("[SiCDox BUILD] DB existente encontrado, removendo para rebuild: %s", db_path)
            # fechar handles não é possível aqui (esperamos que nenhum processo esteja usando),
            # removemos arquivos sqlite auxiliares também (wal/shm).
            for suf in ("", "-wal", "-shm"):
                f = db_p.with_name(db_p.name + suf)
                try:
                    if f.exists():
                        f.unlink()
                except Exception:
                    logger.warning("Não foi possível remover %s (continuando)", f, exc_info=True)
        # remove índice invertido antigo se existir
        if inv_dir.exists():
            logger.info("[SiCDox BUILD] Removendo diretório de índice invertido anterior: %s", inv_dir)
            try:
                # usar rmtree para remover diretório recursivamente
                import shutil

                shutil.rmtree(inv_dir)
            except Exception:
                logger.warning("Falha ao remover índice invertido %s (continuando)", inv_dir, exc_info=True)
    except Exception:
        logger.exception("Erro ao tentar remover DB/índice existente; prosseguindo com build")

    if verbose:
        logger.info("[SiCDox BUILD] Construindo Banco Tokenizado... DB: %s", db_path)

    inv_builder = InvertedIndexBuilder()
    t0 = time.monotonic()

    con = sqlite3.connect(db_path, isolation_level=None)
    try:
        con.execute("PRAGMA page_size=4096")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        # cache_size is in pages; use negative value to specify KB units (e.g. -20000 ~ 20MB depending on page_size)
        try:
            con.execute("PRAGMA cache_size = -20000")
        except Exception:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            title TEXT,
            path TEXT,
            content_hash TEXT
        )
        """)
        con.execute("""
        CREATE TABLE IF NOT EXISTS content_pool (
            hash TEXT PRIMARY KEY,
            token_blob BLOB
        )
        """)

        # Optional index for faster joins
        con.execute("CREATE INDEX IF NOT EXISTS idx_pages_hash ON pages(content_hash)")


        con.execute("BEGIN")
        # Preparações para otimização:
        # - carrega vocab UMA vez antes do loop
        # - reduz max chars tokenizados para diminuir custo
        vocab = TokenizerBridge.get_vocab()
        MAX_TOKENIZE_CHARS = int(os.environ.get("SICDOX_MAX_CHARS", "4000"))

        count = deduplicated = 0
        buf_pages: List[tuple] = []
        seen_hashes = set()
        # Buffer para writes em batch do content_pool: mapa hash->blob
        content_pending: dict[str, bytes] = {}
        CONTENT_FLUSH_BATCH = int(os.environ.get("SICDOX_CONTENT_BATCH", "256"))

        def _flush_content_pending():
            """Insere em bulk o que estiver pendente no content_pool e limpa o buffer."""
            nonlocal content_pending
            if not content_pending:
                return
            items = list(content_pending.items())
            with orn_span("build.sql_insert", category="index"):
                try:
                    # executemany em lote para reduzir overhead
                    con.executemany("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", items)
                except Exception:
                    # fallback item-a-item se algo falhar (mais lento, mas resiliente)
                    logger.debug("bulk insert failed; falling back to single inserts", exc_info=True)
                    for k, v in items:
                        try:
                            con.execute("INSERT OR IGNORE INTO content_pool (hash, token_blob) VALUES (?, ?)", (k, v))
                        except Exception:
                            logger.debug("failed single insert for %s", k, exc_info=True)
            content_pending = {}

        for title, path, html in _iter_zim_entries(zim_path, verbose=verbose):
            with orn_span("build.strip_html", category="index"):
                body = _strip_html(html, max_chars=MAX_TOKENIZE_CHARS)

            if len(body.strip()) < 50:
                continue

            with orn_span("build.tokenize", category="index"):
                try:
                    # tokeniza o corpo e o título (título terá peso maior no índice)
                    body_bytes = body.encode("utf-8")
                    qtoks = vocab.tokenize(body_bytes, add_bos=False)  # lista de ints
                    title_bytes = title.encode("utf-8")
                    ttoks = vocab.tokenize(title_bytes, add_bos=False)
                    # payload armazenado no content_pool: apenas tokens do corpo (economiza espaço)
                    body_arr = array.array("i", qtoks)
                    payload = body_arr.tobytes()
                except Exception:
                    logger.debug("tokenize failed for title=%s", title, exc_info=True)
                    continue

                h = hashlib.md5(payload).hexdigest()

            if h not in seen_hashes:
                seen_hashes.add(h)
                with orn_span("build.zstd_compress", category="index"):
                    compressed = _compress(payload)

                # acumula em memória e escreve em bloco quando atingir CONTENT_FLUSH_BATCH
                content_pending[h] = compressed
                if len(content_pending) >= CONTENT_FLUSH_BATCH:
                    _flush_content_pending()
            else:
                deduplicated += 1

            count += 1
            buf_pages.append((count, title, path, h))

            # Para melhorar relevância, duplicamos tokens do título ao passar ao inverted index
            # (aumenta peso de termos que aparecem no título)
            try:
                combined_tokens = ttoks + ttoks + qtoks  # título tem peso 2
            except Exception:
                combined_tokens = qtoks

            with orn_span("build.inverted_idx", category="index"):
                inv_builder.add_document(count, combined_tokens)

            if len(buf_pages) >= batch_size:
                with orn_span("build.sql_commit", category="index"):
                    con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
                    _flush_content_pending()
                    con.execute("COMMIT")
                    con.execute("BEGIN")
                    buf_pages.clear()
                if verbose:
                    logger.info("[BUILD] %d artigos tokenizados...", count)

        if buf_pages:
            con.executemany("INSERT INTO pages (id, title, path, content_hash) VALUES (?,?,?,?)", buf_pages)
        con.execute("COMMIT")

    except Exception:
        logger.exception("Erro durante build_index; rollback")
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()

    inv_builder.finalize()
    inv_dir = INDEX_DIR / source_id
    inv_builder.write(inv_dir)

    if verbose:
        logger.info("[BUILD] Concluído: %d matrizes (Dedup: %d) em %.1fs", count, deduplicated, time.monotonic() - t0)

    return Path(db_path)

# ---------------------------------------------------------------------------
# SEARCH LOCAL
# ---------------------------------------------------------------------------

def _simple_query_tokens(text: str) -> list[int]:
    # Fallback rápido: hash de n-grams ou bytes simples
    # NOTE: não compatível 1:1 com tokens do GGUF, mas dá resultados rápidos
    # Implementação simples: split por palavras e use hash modulo 2^31
    toks = []
    for w in re.findall(r"[A-Za-z0-9]+", text.lower()):
        h = int(hashlib.md5(w.encode("utf-8")).hexdigest()[:8], 16)
        toks.append(h & 0x7fffffff)
    return toks

def search_local(query: str, source_id: str, limit: int = 3) -> List[LocalResult]:
    if not query.strip():
        return []

    db_path = str(_source_id_to_db(source_id))
    if not Path(db_path).exists():
        return []

    t_start = time.perf_counter()
    label = f"{source_id}-local"

    try:
        con = sqlite3.connect(db_path, check_same_thread=False)
        con.execute("PRAGMA query_only=1")
        results: List[LocalResult] = []
        doc_ids: List[int] = []

        inv_dir = INDEX_DIR / source_id
        if inv_dir.exists():
            try:
                with InvertedIndexSearcher(inv_dir) as searcher:
                    if _env_bool("SICDOX_FAST_MODE"):
                        query_tokens = _simple_query_tokens(query)
                    else:
                        vocab = TokenizerBridge.get_vocab()
                        query_tokens = vocab.tokenize(query.encode("utf-8"), add_bos=False)
                    doc_ids = searcher.search(query_tokens, limit=limit)
            except Exception:
                logger.debug("Inverted index search failed; falling back", exc_info=True)

        if not doc_ids:
            # Fallback por título: prioriza igualdade, depois prefixo, depois substring
            q_esc = _like_escape(query)
            exact = query
            starts = f"{q_esc}%"
            contains = f"%{q_esc}%"
            rows = con.execute(
                "SELECT p.id, p.title FROM pages p WHERE p.title LIKE ? ESCAPE '\\\\' OR p.title LIKE ? ESCAPE '\\\\' OR p.title LIKE ? ESCAPE '\\\\' LIMIT ?",
                (exact, starts, contains, limit),
            ).fetchall()
            # ordena manualmente: igualdade -> prefixo -> contains, e depois por tamanho do título
            ordered = []
            for r in rows:
                pid, ptitle = r
                pl = ptitle.lower()
                ql = query.lower()
                if pl == ql:
                    score = 0
                elif pl.startswith(ql):
                    score = 1
                elif ql in pl:
                    score = 2
                else:
                    score = 3
                ordered.append((score, len(ptitle), pid))
            ordered.sort()
            doc_ids = [t[2] for t in ordered][:limit]

        for doc_id in doc_ids:
            row = con.execute(
                "SELECT p.title, p.path, c.token_blob FROM pages p JOIN content_pool c ON p.content_hash = c.hash WHERE p.id = ?",
                (doc_id,),
            ).fetchone()
            if row:
                title, path, blob = row
                try:
                    decompressed_bytes = _decompress(blob)
                except RuntimeError as e:
                    logger.warning("search_local: skipping doc %s due to decompression error: %s", doc_id, e)
                    continue
                body = TokenizerBridge.bytes_to_text(decompressed_bytes)
                if not body.strip():
                    logger.debug("search_local: doc %s produced empty body after decode; skipping", doc_id)
                    continue

                body = re.sub(r"\n\s*\n", "\n\n", body).strip()
                if body.lower().startswith(title.lower()):
                    body = body[len(title):].strip()

                results.append(LocalResult(label, title, body, path))

        con.close()
        if _env_bool("VULCAN_TELEMETRY"):
            logger.info("[VULCAN PROFILER] search_semantic(%s) C++ ZSTD: %.2fms", source_id, (time.perf_counter() - t_start) * 1000)
        return results

    except Exception:
        logger.exception("search_local failed")
        return []


# ---------------------------------------------------------------------------
# INFO / LIST
# ---------------------------------------------------------------------------

def index_info(source_id: str) -> dict:
    db_path = _source_id_to_db(source_id)
    zim = _find_zim_for_source(source_id)
    info = {"source_id": source_id, "exists": False, "articles": 0, "mode": "Aguardando Build", "zim_path": str(zim) if zim else "?"}
    if db_path.exists():
        try:
            con = sqlite3.connect(db_path)
            info["articles"] = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
            info["exists"] = True
            info["mode"] = "SiCDox (Tokenized)" if meta.get("sicdox_ver") else "Texto Puro"
            con.close()
        except Exception:
            logger.debug("index_info failed for %s", source_id, exc_info=True)
    return info


def list_indexes() -> List[dict]:
    seen, result = set(), []
    if INDEX_DIR.exists():
        for db_file in sorted(INDEX_DIR.glob("*.db")):
            sid = db_file.stem
            seen.add(sid)
            result.append(index_info(sid))
    if ZIM_DIR.exists():
        for zim_file in sorted(ZIM_DIR.glob("*.zim")):
            sid = _zim_to_source_id(zim_file)
            if sid not in seen:
                result.append({"source_id": sid, "articles": 0, "zim_path": str(zim_file), "mode": "Aguardando Build", "exists": False})
                seen.add(sid)
    return result


# ---------------------------------------------------------------------------
# ZIM header probe / diagnose
# ---------------------------------------------------------------------------

_ZIM_MAGIC = 0x044D495A
_ZIM_HEADER_SIZE = 80


def _read_zim_header(zim_path: str) -> dict:
    with open(zim_path, "rb") as f:
        raw = f.read(_ZIM_HEADER_SIZE)
    if len(raw) < _ZIM_HEADER_SIZE:
        raise ValueError(f"Arquivo muito pequeno ({len(raw)} bytes)")
    magic, major, minor = struct.unpack_from("<IHH", raw, 0)
    if magic != _ZIM_MAGIC:
        raise ValueError(f"Magic inválido: 0x{magic:08X}")
    entry_count, cluster_count = struct.unpack_from("<II", raw, 24)
    return {"version": f"{major}.{minor}", "uuid": raw[8:24].hex(), "entry_count": entry_count, "cluster_count": cluster_count}


def probe_zim(zim_path: str) -> None:
    try:
        info = _read_zim_header(zim_path)
        size_mb = round(Path(zim_path).stat().st_size / 1_048_576, 1)
        print(f"\n  [PROBE] {Path(zim_path).name}")
        print(f"  Versão ZIM:    {info['version']}")
        print(f"  Entradas:      {info['entry_count']:,}")
        print(f"  Clusters:      {info['cluster_count']:,}")
        print(f"  UUID:          {info['uuid']}")
        print(f"  Tamanho:       {size_mb} MB")
    except Exception as e:
        print(f"  [PROBE] FALHOU: {e}")


def diagnose_zim(zim_path: str, n: int = 20) -> None:
    try:
        import pyzim
    except ImportError:
        print("  pyzim não instalado.")
        return

    print(f"\n  [DIAGNOSE] {Path(zim_path).name} — primeiras {n} entradas")
    print(f"  {'#':<4} {'redirect':<10} {'namespace':<12} {'mime':<30} {'content_bytes':<14} {'title'}")
    print(f"  {'-'*100}")

    with pyzim.Zim.open(str(Path(zim_path).absolute()), mode="r") as zim:
        for i, entry in enumerate(zim.iter_entries()):
            if i >= n:
                break
            is_redir = getattr(entry, "is_redirect", "?")
            ns = getattr(entry, "namespace", "?")
            if isinstance(ns, bytes):
                ns = ns.decode("utf-8", errors="ignore")
            mime = getattr(entry, "mimetype", None) or getattr(entry, "mime_type", "?")
            if callable(mime):
                mime = mime()
            if isinstance(mime, bytes):
                mime = mime.decode("utf-8", errors="ignore")
            title = getattr(entry, "title", "?")
            if isinstance(title, bytes):
                title = title.decode("utf-8", errors="ignore")
            content = _read_entry_content(entry)
            clen = len(content) if content else 0
            chead = ""
            if content:
                chead = content[:60].replace(b"\n", b" ").decode("utf-8", errors="ignore")
            print(f"  {i:<4} {str(is_redir):<10} {str(ns):<12} {str(mime)[:28]:<30} {clen:<14} {str(title)[:40]}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="local_index", description="ORN LocalIndex v6.0 — SiCDox (Semantic Compression)")
    parser.add_argument("--gguf", help="Caminho para o arquivo .gguf (sobe para SICDOX_GGUF)")
    parser.add_argument("--verbose", action="store_true", help="Ativa modo verboso")

    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("probe", help="Ler header do zim")
    b = sub.add_parser("build", help="Construir índice tokenizado")
    b.add_argument("zim", help="Caminho do arquivo .zim")
    b.add_argument("source_id", nargs="?", help="Source ID opcional")
    s = sub.add_parser("search", help="Buscar no índice local")
    s.add_argument("source_id", help="Source ID")
    s.add_argument("query", nargs=argparse.REMAINDER, help="Termos de busca")
    i = sub.add_parser("info", help="Informação do índice")
    i.add_argument("source_id", help="Source ID")
    sub.add_parser("list", help="Listar índices e ZIMs disponíveis")
    sub.add_parser("diagnose", help="Diagnose ZIM (primeiras entradas)").add_argument("zim", nargs=1)

    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.gguf:
        os.environ[_GGUF_PATH_ENV] = args.gguf

    # Chronos (opcional)
    chronos_recorder = None
    try:
        from doxoade.chronos import chronos_recorder

        class FakeCommand:
            name = f"INDEX-{args.cmd.upper() if args.cmd else 'NONE'}"

        class FakeCtx:
            invoked_subcommand = None
            command = FakeCommand()
            obj = {}

        chronos_recorder.start_command(FakeCtx())
        logger.info("[TELEMETRY] Chronos Nexus ativado! (Sessão: %s)", chronos_recorder.session_uuid)
    except Exception as e:
        logger.debug("Chronos não iniciado: %s", e)

    exit_code = 0
    t_start_global = time.perf_counter()

    try:
        if args.cmd == "probe":
            probe_zim(args.zim)
        elif args.cmd == "build":
            build_index(args.zim, source_id=getattr(args, "source_id", None))
            try:
                GLOBAL_TELEMETRY.flush_json("telemetry/local_index_build.json")
                logger.info("[TELEMETRY] ORN Spans salvos em telemetry/local_index_build.json")
            except Exception:
                logger.debug("Não foi possível salvar GLOBAL_TELEMETRY", exc_info=True)
        elif args.cmd == "search":
            q = " ".join(args.query or [])
            results = search_local(q, args.source_id)
            elapsed = round((time.perf_counter() - t_start_global) * 1000, 2)
            if not results:
                print("\n  Nenhum resultado para a busca.")
            else:
                for r in results:
                    print(f"\n  [{r.source}] {r.title}\n  {r.body[:400]}")
            print(f"\n  Tempo: {elapsed}ms | {len(results)} resultado(s)")
        elif args.cmd == "info":
            for k, v in index_info(args.source_id).items():
                print(f"  {k:<12}: {v}")
        elif args.cmd == "list":
            for info in list_indexes():
                print(f"  {info['source_id']:<45} {info.get('articles', 0):>8}  {info.get('mode', '?')}")
        elif args.cmd == "diagnose":
            diagnose_zim(args.zim[0], n=20)
        else:
            parser.print_help()

    except Exception as e:
        exit_code = 1
        logger.exception("CLI command failed")
        raise

    finally:
        if chronos_recorder:
            duration_ms = (time.perf_counter() - t_start_global) * 1000
            try:
                chronos_recorder.end_command(exit_code, duration_ms)
                logger.info("[TELEMETRY] Dados gravados no banco de auditoria Doxoade.")
            except Exception:
                logger.debug("Erro ao salvar log do Chronos", exc_info=True)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(_cli_main())
