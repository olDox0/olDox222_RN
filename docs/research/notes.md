# ORN — Research Notes
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## [2026.02.19] Relatorio de Memoria -- Prototipo Anterior

Fonte: relatorio tecnico interno sobre Qwen + LLaMA em ambientes edge.

### Problema Central
Qwen e LLaMA foram pensados para datacenter, nao para edge/desktop.
Quem aceita isso perde controle do sistema.
Quem domina memoria, manda no jogo.

### Causas Identificadas

  KV-cache (vilao silencioso):
    Cada token novo -> chaves + valores em todas as camadas
    Contexto grande = vazamento controlado de RAM
    Em multi-request vira desastre

  Pesos (quantizacao):
    7B FP16 = 14-16 GB
    Camadas de atencao duplicam buffers

  Fragmentacao:
    Alocadores genericos (CUDA/malloc) fragmentam rapido
    Load/unload de modelos piora tudo

### Solucoes que Funcionam

  Quantizacao agressiva (obrigatorio):
    INT4: surpreendentemente boa para codigo
    Qwen2.5-Coder em INT4 ainda e extremamente util

  KV-cache inteligente (muda tudo):
    Sliding window: tokens fora de active_window -> embedding resumido
    Resultado: ate 60-80% menos memoria
    context = [system | task | constraints | active_window]

  Cache externo CPU/mmap:
    Camadas inferiores -> CPU
    Camadas finais -> GPU
    Swap inteligente por prioridade

  Load parcial de camadas:
    Inferencia simples -> 30-50% das camadas
    Raciocinio pesado -> full stack
    Controlado via n_gpu_layers no ORN

### Decisoes Incorporadas no ORN
  n_ctx = 2048          (nao 4096 -- conservador)
  active_window = 1024  (50% do n_ctx)
  max_tokens = 512      (25% do n_ctx -- resposta concisa)
  n_gpu_layers = 0      (CPU-only seguro para desktop)
  ttl_seconds = 300     (modelo desce apos 5 min inatividade)
  ContextWindow sliding window implementada em llm_bridge.py

---

## [2026.02.19] Comparativo Qwen vs LLaMA

  Qwen:
    + Melhor para codigo
    + Mais tolerante a quantizacao
    - Um pouco mais pesado

  LLaMA:
    + Comunidade enorme
    + Mais ferramentas
    - KV-cache mais agressivo

  Decisao: Qwen INT4 como padrao. LLaMA INT4 so quando necessario.

---

## [2026.02.19] Archaeology Layers -- Logica Perdida Recuperada

O chief_dossier.json revelou funcoes importantes que foram apagadas
em commits anteriores do prototipo OIA. Registradas como notas para
recuperacao nas fases certas.

  llm_bridge.py (2026-02-01, layer 1):
    generate_plan(user_intent, context_graph_snippet):
      Gera Meta-Acao harmonizada com o estado atual do Grafo TGF.
      prompt = f'CONTEXTO ATUAL (TGF):\n{context_graph_snippet}\n\n
                INTENCAO DO ARQUITETO: {user_intent}'
      Recuperar na Fase 4.

  concept_mapper.py (2026-01-26, layer 2):
    map_file(file_path):
      with open(file_path) as f: tree = ast.parse(f.read())
      return self.visit_node(tree)

    visit_node(node):
      Percorre AST recursivamente, gera dict com cid, type, relations.
      meta_action = "SENSE_SINTAX" para FunctionDef.
      Recuperar na Fase 2.

  thinking/core.py (2025-12-27, layer 2):
    ponder(input_context):
      key_concepts = self._extract_concepts(input_context)
      related_memories = self._query_associations(key_concepts)
      plan = self._formulate_plan(key_concepts, related_memories)
      Sistema 2 -- gera PLANO antes de agir, nao codigo diretamente.
      Recuperar na Fase 4.

---

## [2026.02.19] doxcolors -- Sistema de Cores Interno

Status: incubando. ColorManager em desenvolvimento ativo.
Prototipo: colors.py + color_checkin.py

Abordagem adotada para ORN:
  - Adaptar ColorManager como singleton
  - load_conf() le colors.conf no mesmo diretorio
  - _activate_ansi() via ctypes.windll no Windows
  - Sem colorama, sem rich, zero deps externas

Benchmark observado (doxoade run benchmark.py):
  Import Colorama:     0.03ms -> 0.26ms (variacao)
  Import ColorManager: 17.5ms -> 4.3ms (apos vulcan ignite)
  Vulcan ignite compila 42 candidatos em ~53s
  Apos compilacao: ColorManager 4x mais rapido que colorama

Conclusao: vale a incubacao. ColorManager com Vulcan e superior
em ambientes doxoade. Para MVP do ORN, a versao Python pura ja serve.