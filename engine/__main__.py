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

for _doxo_base in [_doxo_path(__file__).resolve(), *_doxo_path(__file__).resolve().parents]:
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

# 1. Instala MetaFinder primeiro — redireciona imports Python → PYD automaticamente
if callable(_doxo_install_meta_finder) and _doxo_project_root:
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_install_meta_finder(_doxo_project_root)
    except Exception:
        # não falha a execução do bootstrap — metas podem já estar instalados
        pass
    finally:
        _doxo_install_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 2. Tenta usar o loader "embedded" (safe wrapper com safe_call + checagem de assinatura)
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
                        # activate_embedded aplica safe_call e valida assinaturas — preferível
                        _doxo_activate_embedded(globals(), __file__, _doxo_project_root)
                    except Exception:
                        pass

                # Se safe_call está exposto, aplicamos um pass de segurança a MÓDULOS JÁ CARREGADOS
                # Isso resolve o caso em que o .pyd já foi importado antes do bootstrap
                if callable(_doxo_safe_call):
                    try:
                        import sys as _d_sys
                        _bin_dir = _doxo_path(_doxo_project_root) / ".doxoade" / "vulcan" / "bin"
                        for mname, mod in list(_d_sys.modules.items()):
                            try:
                                mfile = getattr(mod, "__file__", "")
                                if not mfile:
                                    continue
                                mpath = _doxo_path(mfile)
                                # só módulos que residem na foundry bin
                                if _bin_dir in mpath.parents:
                                    # iterar sobre atributos nativos e aplicar safe_call
                                    for attr in dir(mod):
                                        if not attr.endswith("_vulcan_optimized"):
                                            continue
                                        native_obj = getattr(mod, attr, None)
                                        if not callable(native_obj):
                                            continue
                                        base = attr[: -len("_vulcan_optimized")]
                                        try:
                                            setattr(mod, base, _doxo_safe_call(native_obj, getattr(mod, base, None)))
                                        except Exception:
                                            # não falha a importação; continuamos
                                            continue
                            except Exception:
                                continue
                    except Exception:
                        pass
except Exception:
    pass
finally:
    _doxo_embedded_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 3. Fallback: runtime.activate_vulcan (mantém compatibilidade retroativa)
# Chamamos em try/except para não interromper o fluxo caso o runtime injete de forma insegura.
if callable(_doxo_activate_vulcan):
    _doxo_t = _doxo_time.monotonic()
    try:
        _doxo_activate_vulcan(globals(), __file__)
    except Exception:
        # não propaga erro — se falhar, o projeto seguirá com implementações Python originais
        pass
    finally:
        _doxo_fallback_ms = int((_doxo_time.monotonic() - _doxo_t) * 1000)

# 4. Diagnóstico opcional (útil para startup lento em servidores externos)
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
# ORN/engine/__main__.py

from pathlib import Path
import importlib.util


def _load_python_cli_fallback():
    """Carrega `engine/cli.py` direto do arquivo para contornar wrappers inválidos."""
    cli_file = Path(__file__).resolve().parent / "cli.py"
    spec = importlib.util.spec_from_file_location("_orn_cli_fallback", str(cli_file))
    if not spec or not spec.loader:
        raise RuntimeError("Falha ao criar spec para fallback de engine.cli")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.cli


def _is_wrapper_signature_type_error(exc: TypeError) -> bool:
    """Retorna True quando o TypeError parece ser de assinatura do wrapper compilado."""
    msg = str(exc)
    signature_tokens = (
        "positional argument",
        "required positional argument",
        "unexpected keyword argument",
    )
    wrapper_tokens = ("cli_vulcan_optimized", "optimized", "argument")
    return any(token in msg for token in signature_tokens) and any(
        token in msg for token in wrapper_tokens
    )


def main():
    from engine.cli import cli

    try:
        cli()
    except TypeError as exc:
        # Vulcan pode substituir o wrapper do Click por uma função com assinatura
        # incompatível (ex.: espera `ctx`). Nesse caso, caímos para Python puro.
        if not _is_wrapper_signature_type_error(exc):
            raise
        fallback_cli = _load_python_cli_fallback()
        fallback_cli()


if __name__ == "__main__":
    main()
