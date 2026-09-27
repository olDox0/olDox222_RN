---

# 📑 OIA_CORE_ARCHITECTURE.md (Draft v1.0)

**Status:** Em Redação (Protocolo PASC 8.4)
**Codinome:** Tiered-Graph Framework (TGF)
**Motor:** DoxoNet v4.0 (NumPy-Only)

## 1. Visão Geral: O Cérebro Relacional
O OIA não é um preditor de texto; é um **Processador de Intencionalidade**. Ele utiliza uma arquitetura híbrida onde a intuição (Neural) propõe caminhos em um grafo, e a lógica (Simbólica) valida a integridade desses caminhos.

## 2. O Código Genético Reciclado (Herança ORN)
Preservaremos do laboratório anterior os seguintes "genes" de sucesso:
1.  **DoxoAct (Ativação Periódica):** Mantida para introduzir variância controlada em aprendizados de sintaxe.
2.  **Fused Gates (L0 Math):** A técnica de concatenar pesos (Input + Hidden) será o padrão do Kernel para maximizar o cache da CPU.
3.  **Pushdown Automaton (System 2):** A lógica de pilha do `doxologic.py` será o "vocalizador" final do Grafo, garantindo que a saída seja sempre parseável.
4.  **Quantização 8-bit:** Obrigatória para a persistência de pesos (Aegis-Safe).

## 3. Tiered-Graph Framework (TGF)
A estrutura de dados principal é um **Grafo Hierárquico de Identificadores Numéricos Flexíveis**.

### L0: Tier Sistêmico (The Map)
*   **Representação:** IDs que simbolizam módulos e dependências globais.
*   **Função:** Impedir que uma alteração em um Expert de IO afete o Kernel Matemático sem autorização do MF-TD.

### L1: Tier de Contrato (The Signature)
*   **Representação:** IDs para assinaturas de funções (Args, Returns, Exceptions).
*   **Justificativa:** Combate a **Erosão Funcional**. O sistema "sente" a quebra de um contrato antes mesmo de rodar o código.

### L2: Tier de Fluxo (The Action)
*   **Representação:** IDs para operações atômicas (`A -> B`).
*   **Função:** Onde ocorre o cruzamento sofisticado. Ex: O ID de um "Erro de Linter" aponta para o ID de uma "Correção Histórica" via aresta de `SOLVED_BY`.

## 4. M2A2 & Blackboard (The Memory)
*   **Blackboard:** Um espaço de trabalho em NumPy onde os Experts competem. O `DoxoBoard` usará **Snapshots de Contexto** (Snippets) para que o Arquiteto Humano possa racionalizar as decisões da IA (PASC-4).
*   **M2A2:** O sistema de recompensa. Caminhos no grafo que levam a um `check` verde recebem incremento de peso sináptico nos IDs envolvidos.

---
