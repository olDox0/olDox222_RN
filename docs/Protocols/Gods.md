# Programming Gods — Mapeamento Semantico
**CR:** 2026.01.07 | **AT:** 2026.02.19

Sistema de mapeamento semantico que associa cada modulo/componente
de software a uma divindade que representa seu papel arquitetural.
Usado em todos os projetos olDox222 como linguagem comum de design.

---

## Panteon Grego

  Zeus        Kernel / Orquestrador / Root
              Controla permissoes, decisoes globais.
              ORN: SiCDoxExecutive -- autoridade central do sistema.

  Hera        Banco de dados / Schema / Consistencia
              Garante integridade e relacoes.
              ORN: Contratos de API (GoalResult, BridgeConfig).

  Poseidon    Streams / I/O / Redes / Analise Forense
              Fluxos continuos, instaveis.
              ORN: Protocolo Poseidon (rescue, analise forense, Sherlock).

  Hades       Storage profundo / Arquivamento
              Onde dados "morrem" mas permanecem.
              ORN: DoxoBoard (blackboard de hipoteses da sessao).

  Atena       Arquitetura de software / Design patterns
              Planejamento antes do codigo.
              ORN: ExecutivePlanner -- estrategia antes de qualquer execucao.

  Ares        Codigo hackeado / Forca bruta
              Funciona, mas e feio, perigoso.
              ORN: lixao/ -- material bruto sem refatoracao.

  Apolo       Codigo limpo / APIs bem definidas
              Elegante, legivel.
              ORN: Display -- clareza e ordem no terminal.

  Artemis     Scripts standalone / Ferramentas CLI
              Faz uma coisa, faz bem.
              ORN: cli.py -- a identidade do projeto inteiro.

  Hefesto     Build systems / Toolchains
              Transforma ideia em artefato.
              ORN: SiCDoxBridge -- transforma prompt em codigo.

  Hermes      Mensageria / APIs / Protocolos
              Conecta tudo.
              ORN: Protocolo Lazaro, integracao doxoade x ORN.

  Demeter     Pipelines de dados
              Plantar -> processar -> colher.
              ORN: Fases do roadmap (Fase 1 -> 2 -> 3 -> 4 -> 5).

  Afrodite    UI/UX
              Se ninguem gosta de usar, morreu.
              ORN: ColorManager + colors.conf.

  Dionisio    Prototipagem / Pesquisa
              Onde surgem ideias novas.
              ORN: lixao/ -- 66 arquivos de prototipagem do OIA.

---

## Panteon Egipcio

  Ra          Clock global / Main loop / Fonte de energia
              ORN: __main__.py -- o loop principal.

  Osiris      Persistencia forte / Estado consistente
              Renascimento apos falhas.
              ORN: VectorDB -- memoria semantica de sessao.

  Isis        Middleware / Orquestracao logica
              Junta partes quebradas.
              ORN: IntentionBrain (classificador) + Associator.

  Horus       Observabilidade / Watchdog
              Ve tudo, reage rapido.
              ORN: GraphInspector -- supervisao do grafo interno.

  Set         Falhas, bugs, ataques, ruido
              Tudo que tenta derrubar o sistema.
              Set nao e "mau" -- sistemas maduros esperam Set.
              ORN: inputs invalidos, respostas vazias, FileNotFoundError.

  Anubis      Validacao / Seguranca / Compliance
              Decide o que passa ou morre.
              ORN: SiCDoxValidator -- valida todo output do LLM.

  Ma'at       Invariantes do sistema
              O que nunca pode quebrar.
              ORN: Sherlock -- verifica coerencia das hipoteses.

  Thoth       Linguagens / Compiladores / IA simbolica
              Da forma ao pensamento.
              ORN: Atlas + ConceptMapper -- AST e grafo de conceitos.

  Ptah        Implementacao concreta / Baixo nivel
              Ideia vira maquina.
              ORN: extensoes Cython (.pyx / .pyd) em .doxoade/vulcan/

  Sekhmet     Resposta ativa a incidentes
              Ataca para proteger.
              ORN: doxoade check --security / Protocolo Poseidon.

  Hathor      UX humana
              Sistema que nao cansa o usuario.
              ORN: Display.thinking(), Display.banner() -- feedback imediato.

  Bastet      Sandbox / Isolamento
              Protege sem agressividade.
              ORN: tests/ (zona de quarentena OSL-19).

---

## Regra de Aplicacao

Ao criar um novo modulo, defina seu deus no cabecalho:
  # God: Zeus -- papel do modulo aqui

Ao revisar um modulo, verifique se o comportamento condiz com seu deus.
Um modulo de Hefesto que comeca a "tomar decisoes" virou Zeus -- refatorar.

---

## Nucleos Arquiteturais

  Sistema robusto    = Ma'at + Anubis + Osiris
  Sistema inteligente = Thoth + Isis
  Sistema resiliente  = espera Set
  Sistema morto       = ignora Ra (tempo/energia)

  ORN nucleo ideal: Thoth + Ma'at + Osiris + Horus