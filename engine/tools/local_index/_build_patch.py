# -*- coding: utf-8 -*-
# engine/tools/local_index/_build_patch.py
"""
Patch de build_index() para usar o pipeline em rounds.

SUBSTITUIÇÃO no _build.py real — apenas o trecho do loop principal.
Tudo o mais (init DB, check_resume, cleanup_stale) permanece igual.

ANTES (loop ansioso — causava 158k commits):
─────────────────────────────────────────────
    con.execute("BEGIN")
    for idx, title, path, html in _iter_zim_entries(zim_path, ...):
        result = _process_entry(...)
        if result:
            con.executemany("INSERT OR IGNORE ...", [...])
            con.execute("COMMIT")          ← 1 commit por artigo!
            con.execute("BEGIN")
            inv_builder.add_document(...)

DEPOIS (pipeline em rounds — 1 commit por 500 artigos):
─────────────────────────────────────────────────────────
    from engine.tools.local_index._tokenizer import TokenizerBridge
    from engine.tools.local_index._pipeline  import run_pipeline

    tok = TokenizerBridge()
    tok.pitstop()      # detecta: server | vocab_only | hash

    stats = run_pipeline(
        zim_path    = zim_path,
        con         = con,
        inv_builder = inv_builder,
        start_scanned = resume_state.last_scanned,
        tok         = tok,
    )
    tok.close()
"""

# ─── Trecho completo para substituição direta em build_index() ───────────────

def _build_index_loop_patch(
    zim_path,
    con,
    inv_builder,
    resume_state,
    use_tokenizer_pitstop: bool = True,
) -> dict:
    """
    Substitui o loop de build_index() pelo pipeline em rounds.
    Retorna stats do pipeline.

    Parâmetros correspondem às variáveis locais do build_index() original.
    """
    from engine.tools.local_index._pipeline  import run_pipeline   # noqa
    from engine.tools.local_index._tokenizer import TokenizerBridge # noqa

    tok = None
    if use_tokenizer_pitstop:
        tok = TokenizerBridge()
        mode = tok.pitstop()
        import logging
        logging.getLogger("engine.tools.local_index.build").info(
            "[BUILD] Pitstop pronto — modo=%s  COMMIT_BATCH=%d",
            mode,
            1000,  # COMMIT_BATCH
        )

    try:
        stats = run_pipeline(
            zim_path      = zim_path,
            con           = con,
            inv_builder   = inv_builder,
            start_scanned = getattr(resume_state, "last_scanned", 0),
            tok           = tok,
            progress_every= 400,
            verbose       = True,
        )
        
        # --- ADICIONE ESTAS DUAS LINHAS AQUI ---
        import logging
        logging.getLogger("engine.tools.local_index.build").info("[BUILD] Otimizando banco de dados (VACUUM)... isso pode levar alguns segundos.")
        con.execute("VACUUM")
        # --------------------------------------

    finally:
        if tok is not None:
            tok.close()

    return stats