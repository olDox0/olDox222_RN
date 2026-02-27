# ORN — Security
**CR:** 2026.02.19 | **AT:** 2026.02.19

---

## Modelo de Ameaca

O ORN e uma ferramenta de desenvolvimento local. Nao expoe endpoints de rede,
nao armazena dados sensiveis em cloud, nao requer autenticacao remota.
As principais superficies de ataque sao:

  1. Injecao de prompt via arquivos de contexto (--file)
  2. Output malicioso do LLM (codigo que o usuario pode executar)
  3. Acesso a arquivos fora do projeto via ConceptMapper / _read_file_safe
  4. Dependencias comprometidas (supply chain, OSL-13)

---

## Protecoes Implementadas

### Contexto de arquivo (--file)
  - max_chars=3000 em _read_file_safe() -- limita injecao de contexto gigante
  - errors="replace" no open() -- nao crasha em encoding exotico
  - OSError capturado -- retorna "" se nao conseguir ler (OSL-7)

### Output do LLM
  - SiCDoxValidator (Anubis) valida todo output antes de exibir
  - Para lang="python": ast.parse() obrigatorio -- codigo sintaticamente invalido e rejeitado
  - orn fix --apply: requer validacao sintatica; backup automatico antes de sobrescrever

### Zona de quarentena (OSL-19)
  - tests/ nao pode ser importado por modulos de producao (OSL-19.1)
  - doxoade run recusa arquivos em tests/ sem --test-mode (OSL-19.2)
  - Scripts sensiveis verificam DOXOADE_AUTHORIZED_RUN (OSL-19.3)

### Lixao
  - lixao/ e referencia read-only -- nao e importado pelo engine/
  - Codigo do lixao nao e executado automaticamente

---

## Supply Chain (OSL-13)

Dependencias minimas e intencionais:

  click>=8.1          -- CLI. Bem auditada, mantida ativamente.
  numpy>=1.26         -- VectorDB. Stdlib de facto para computacao numerica.
  llama-cpp-python    -- Instalacao manual via wheel pre-compilada no Windows.
                         Verificar versao: python -c "import llama_cpp; print(llama_cpp.__version__)"

Removidas deliberadamente:
  colorama  -> substituido por doxcolors (zero deps, ctypes puro)
  rich      -> substituido por Display + ColorManager

Recomendacoes:
  - Pinagem de versao em requirements.txt (OSL-13)
  - Verificar SHA dos wheels antes de instalar em ambientes sensiveis
  - doxoade install --optimize para detectar pacotes nao utilizados

---

## Consideracoes sobre o Modelo

  - Modelo executado 100% local -- nenhum dado enviado para servidores externos
  - Q4_K_M: quantizacao reduz superficie de ataque de precisao numerica
  - system_prompt define identidade e restricoes do modelo (BridgeConfig)
  - Nao ha mecanismo de fine-tuning no ORN -- modelo e read-only
  - Outputs do modelo sao sempre validados pelo Validator antes de exibicao

---

## Auditoria com doxoade

  doxoade check engine/ -s           -- Auditoria Aegis (Bandit/Safety)
  doxoade check engine/ --security   -- Varredura de seguranca
  doxoade canonize --run-tests       -- Snapshot sagrado com testes
  doxoade regression-test            -- Compara com Canone