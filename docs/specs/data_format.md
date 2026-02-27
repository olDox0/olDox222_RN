# ORN — Data Format Specification
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## doxoade_atlas.json

Mapa funcional de conceitos AST -> IDs simbolicos.
Carregado pelo Atlas (Thoth) na inicializacao.

Estrutura:
  {
    "version": "1.0",
    "node_types": {
      "FunctionDef":  { "cid": 1,  "meta_action": "SENSE_SINTAX" },
      "ClassDef":     { "cid": 2,  "meta_action": "SENSE_STRUCT" },
      "Import":       { "cid": 10, "meta_action": "SENSE_DEP"    },
      "Call":         { "cid": 20, "meta_action": "SENSE_INVOKE" },
      "Assign":       { "cid": 30, "meta_action": "SENSE_STATE"  }
    },
    "meta_actions": {
      "SENSE_SINTAX": "Detecta definicao de funcao",
      "SENSE_STRUCT": "Detecta definicao de classe",
      "SENSE_DEP":    "Detecta dependencia externa",
      "SENSE_INVOKE": "Detecta chamada de funcao",
      "SENSE_STATE":  "Detecta mutacao de estado"
    }
  }

Geracao: ia_tools/doxoade_atlas_gen.py -> gerar_atlas_funcional()
Local:   data/doxoade_atlas.json
Regra:   Nao editar manualmente. Regenerar via: orn graph --rebuild

---

## seed_graph.json

Grafo semente do sistema simbolico. Gerado na primeira execucao do
ConceptMapper sobre o proprio engine/.

Estrutura de no:
  {
    "cid":        1,
    "type":       "FunctionDef",
    "oia_id":     42,
    "name":       "process_goal",
    "meta_action":"SENSE_SINTAX",
    "relations":  [ { "cid": 20, "type": "Call", ... } ]
  }

Local:  data/seed_graph.json
Origem: lixao/old/ia_tools/seed_graph.json (127719 bytes -- migrar na Fase 2)

---

## data/session/ -- Persistencia de Sessao

Arquivos criados em runtime pelo Executive. Formato JSON por sessao.

  data/session/{timestamp}_{intent}.json

Estrutura:
  {
    "session_id":  "20260219_143022",
    "intent":      "think",
    "prompt":      "...",
    "output":      "...",
    "elapsed_s":   1.234,
    "board":       { "hypotheses": [...], "causal_links": [...] },
    "ctx_stats":   { "turns": 3, "token_est": 412, "max_tokens": 1024 }
  }

Regra OSL-3: max 500 arquivos em session/ -- rotacao por data (Fase 3).

---

## cerebro_*.pkl -- Dados do Prototipo Anterior

  cerebro_codex.pkl    750KB   vocabulario e pesos LSTM (old/doxolang.py)
  cerebro_logos.pkl    220KB   estado logico (old/doxologic.py)
  cerebro_vencedor.pkl  61KB   melhor checkpoint de treinamento

Status: arquivados em lixao/. Avaliar reaproveitamento na Fase 3
(VectorDB pode ser inicializado com embeddings extraidos destes pickles).

---

## GoalResult -- Formato de Saida Interno

Ver Architecture/core.md secao SiCDoxExecutive para definicao completa.
Usado como contrato entre Executive e CLI (OSL-7).

---

## colors.conf -- Paleta de Cores

Formato: NOME=codigo_ANSI (sem \033[ e sem m)
Local: engine/ui/colors.conf
Lido por: ColorManager.load_conf() no import de engine/ui/colors.py

Entradas atuais (20):
  RESET, BOLD, DIM
  RED, GREEN, YELLOW, CYAN, WHITE, DARK_GRAY
  BRIGHT_RED, BRIGHT_GREEN, BRIGHT_YELLOW, BRIGHT_CYAN, BRIGHT_WHITE
  ORN_PRIMARY, ORN_SUCCESS, ORN_WARN, ORN_ERROR, ORN_INFO, ORN_DIMMED

Extensao: adicionar entradas ao .conf sem tocar no codigo Python.