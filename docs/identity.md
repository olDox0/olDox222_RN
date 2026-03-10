# ORN — Identity

## Definição

ORN é um runtime de inferência local para LLMs otimizado para **hardware CPU-bound de baixa capacidade**.

Ele existe para tornar **modelos pequenos utilizáveis em máquinas fracas**, priorizando:

- previsibilidade
- estabilidade
- eficiência de CPU
- simplicidade operacional

ORN não é um framework de IA geral.
ORN é um **executor eficiente de modelos locais**.

---

# Problema que o ORN resolve

A maioria das ferramentas de LLM assume:

- GPU
- CPUs modernas
- muita RAM
- infraestrutura pesada

Isso torna esses sistemas **inutilizáveis em hardware modesto**, como:

- CPUs Atom / Silvermont
- Celeron de baixo consumo
- laptops antigos
- servidores pequenos
- ambientes offline

ORN resolve exatamente esse problema.

Ele permite rodar LLMs locais com:

- controle fino de CPU
- baixo consumo de memória
- comportamento previsível
- telemetria clara

---

# Hardware alvo

ORN é projetado explicitamente para hardware **CPU-bound**.

Exemplos de hardware alvo:

- Intel Atom
- Intel Silvermont
- Celeron N-series
- CPUs antigas sem AVX2
- máquinas com 2-4 cores
- sistemas com pouca RAM

ORN assume que:

- GPU **não existe**
- memória é limitada
- throughput é baixo
- latência importa

---

# Filosofia de Design

ORN segue quatro princípios principais:

### 1. CPU-first

Toda decisão de arquitetura prioriza **eficiência em CPU**.

ORN assume:

- paralelismo limitado
- cache pequeno
- baixa largura de memória

---

### 2. Previsibilidade

ORN evita sistemas opacos.

O usuário deve sempre saber:

- o que está acontecendo
- quanto tempo leva
- quanto recurso está sendo usado

---

### 3. Telemetria obrigatória

Performance não pode ser adivinhada.

ORN mede:

- tempo de inferência
- tokens por segundo
- uso de CPU
- uso de RAM

Isso permite otimização real.

---

### 4. Simplicidade estrutural

ORN evita:

- arquiteturas complexas
- dependências pesadas
- abstrações desnecessárias

A estrutura deve ser compreensível rapidamente.

---

# O que o ORN NÃO é

ORN explicitamente **não tenta ser**:

- um agente autônomo
- uma plataforma de IA completa
- um orquestrador de múltiplos modelos
- um framework de ML
- uma interface gráfica pesada
- um sistema GPU-centric

Esses problemas pertencem a outros projetos.

---

# O que o ORN faz

ORN tem responsabilidades claras:

1. carregar modelos GGUF
2. executar inferência local
3. controlar parâmetros de execução
4. registrar telemetria de performance
5. fornecer interface CLI previsível

Nada além disso é garantido.

---

# Escopo do projeto

ORN é principalmente:

- uma **ferramenta**
- um **runtime de execução**
- um **sistema de observabilidade de inferência**

Ele não tenta resolver todos os problemas de IA local.

---

# Critério de sucesso

ORN é bem-sucedido se:

- modelos pequenos rodam de forma estável
- hardware fraco continua utilizável
- inferência é previsível
- otimizações são mensuráveis

Se o ORN exigir hardware moderno para funcionar bem,
então o projeto falhou em seu objetivo.

---

# Regra central

> ORN existe para tornar **hardware fraco útil novamente**.

## Non-Goals

Para preservar simplicidade, previsibilidade e eficiência em hardware CPU-bound, o ORN **explicitamente não tem os seguintes objetivos**.

### Não ser uma plataforma de IA completa
ORN não pretende substituir sistemas como:

- plataformas de agentes
- pipelines de ML
- frameworks de treinamento
- plataformas de experimentação de modelos

Seu foco é **execução eficiente de inferência local**.

---

### Não depender de GPU

ORN não assume a presença de:

- CUDA
- GPUs dedicadas
- aceleração gráfica especializada

Se GPU estiver disponível, isso é considerado **extra**, não requisito.

A arquitetura sempre prioriza **CPU-bound execution**.

---

### Não rodar modelos grandes

ORN não tem como objetivo rodar:

- modelos >7B
- modelos que exigem grandes quantidades de RAM
- workloads de datacenter

O foco são **modelos pequenos e eficientes**.

---

### Não ser um agente autônomo

ORN não tenta implementar:

- sistemas de agentes
- planejamento automático
- loops autônomos de decisão
- execução de tarefas complexas

ORN executa inferência.  
A lógica de alto nível pertence a **camadas externas**.

---

### Não ter interface pesada

ORN evita:

- interfaces gráficas complexas
- dashboards pesados
- dependências de frontend

A interface principal é **CLI simples e previsível**.

---

### Não esconder o comportamento do sistema

ORN não busca abstrair completamente o runtime.

O usuário deve poder observar:

- tempo de inferência
- uso de CPU
- uso de memória
- tokens por segundo

**Transparência é preferida a conveniência.**

---

### Não otimizar para hardware moderno primeiro

ORN não prioriza:

- CPUs AVX-512
- GPUs modernas
- servidores de alta performance

Esses ambientes já possuem boas ferramentas.

ORN existe para **hardware limitado**.

---

### Não crescer indefinidamente

ORN evita crescimento sem controle.

Se uma funcionalidade exigir:

- arquitetura complexa
- grande aumento de dependências
- mudança da filosofia CPU-bound

então essa funcionalidade **deve existir como projeto separado**.