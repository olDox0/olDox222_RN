# PASC — Pipeline and Automation Standard for Commands
**CR:** 2026.01.07 | **AT:** 2026.02.19

Protocolo interno que define como pipelines de automacao e sequencias
de comandos doxoade devem ser estruturados e executados no ORN.

---

## O que e PASC

PASC define:
  - Como sequencias de comandos sao descritas e executadas
  - Como outputs de uma etapa alimentam a proxima
  - Politica de falha e recuperacao em pipelines
  - Nomenclatura de arquivos .dox e pipelines

---

## Formato de Pipeline (.dox)

  # pipeline_nome.dox
  doxoade comando1 [args]
  doxoade comando2 [args]
  doxoade comando3 [args]

Execucao: doxoade maestro pipeline_nome.dox
Criacao:  doxoade create-pipeline nome.dox comando1 comando2 ...

---

## PASC Numerico -- Versoes de Protocolo

  PASC 1.1   Restauracao de contexto Git no forensics (Poseidon Protocol)
  PASC 6.5   Alias flow = doxoade run --flow (Fase 6.5)

---

## Regras de Pipeline no ORN

### Entrada e Saida
  Cada etapa recebe e retorna GoalResult (contrato OSL-7).
  Falhas nao-fatais: GoalResult(success=False) propaga para etapa seguinte.
  Falhas fatais: pipeline interrompido, estado salvo para recuperacao.

### Comandos ORN em Pipeline
  orn think -> orn audit -> orn fix e a sequencia natural de analise.
  Cada comando pode receber o arquivo do anterior via --file.

  Exemplo de pipeline ORN:
    orn audit main.py --format json > audit_result.json
    orn fix main.py
    doxoade save "fix aplicado via orn"

### Integracao com doxoade auto
  orn pode ser chamado dentro de pipelines doxoade:
    # pipeline_analise.dox
    doxoade check engine/
    orn audit engine/core/llm_bridge.py
    doxoade save "auditoria concluida"

---

## Politica de Falha (OSL-15)

  Falha em etapa critica     -> pipeline para, Display.error(fatal=True)
  Falha em etapa opcional    -> GoalResult(success=False), continua
  Timeout de inferencia      -> bridge.shutdown(), GoalResult com erro
  Modelo nao encontrado      -> first_contact detecta, orienta usuario

---

## Protocolo Poseidon (Analise Forense)

Referenciado em PASC-1.1. Usado pelo doxoade rescue e pelo Sherlock (ORN).

  Fluxo:
    Incidente detectado
    -> Dual Forensic Report (Broken vs Stable)
    -> Restore de contexto Git
    -> Validacao de estado pelo Validator (Anubis)
    -> Registro no Blackboard (Hades)

  No ORN: Sherlock.analisar_falha() implementa a logica forense (Fase 3).

---

## Protocolo Lazaro (Recuperacao)

Acionado quando um modulo falha e precisa ser restaurado ao estado estavel.

  1. Identificar o modulo afetado (doxoade check / doxoade diff)
  2. Verificar git local (doxoade rewind --list)
  3. Restaurar arquivo (doxoade rewind arquivo.py -c {hash})
  4. Validar restauracao (doxoade regression-test)
  5. Salvar estado valido (doxoade save "restauracao Lazaro")

  OSL-20.2: Ao perder material, listar afetados antes de recuperar.
  OSL-20.3: Priorizar sistemas centrais e de uso frequente.

---

## Referencia de Comandos doxoade Relevantes para ORN

  doxoade check engine/        -- auditoria de qualidade
  doxoade check engine/ -s     -- seguranca (Aegis)
  doxoade diff engine/         -- regressoes de funcionalidade
  doxoade intelligence -o dossier.json  -- gerar chief_dossier
  doxoade canonize             -- snapshot sagrado
  doxoade save "mensagem"      -- commit seguro com aprendizado
  doxoade rewind arquivo.py    -- time travel
  doxoade regression-test      -- compara com Canone
  doxoade maestro pipeline.dox -- executa pipeline