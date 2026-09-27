# Diário de Pesquisa ORN - Cronologia

## Fase 1: A Gênese (Visão)
*   **Experimento XOR:** A primeira prova de que a rede podia aprender não-linearidade.
    *   *Resultado:* Sucesso. A rede superou o problema da linearidade inicializando pesos com variância maior.
*   **Reconhecimento de Dígitos (MNIST-8x8):** Aplicação de MLPs em dados reais.
    *   *Descoberta:* O uso de **Momentum** acelerou a convergência de 2000 para 500 épocas.
*   **Seleção Natural:** Implementação de algoritmo genético para escolher o número de neurônios.
    *   *Vencedor:* Arquiteturas mais profundas (Deep) superaram as mais largas.

## Fase 2: O Caos (Segurança)
*   **Ataques Adversariais:** Injeção de ruído matemático imperceptível.
    *   *Resultado:* Uma rede com 99% de precisão foi enganada para confundir um '7' com um '8' em apenas 3 passos de gradiente.
    *   *Conclusão:* Redes puras veem textura, não forma. Necessidade de validação lógica.

## Fase 3: A Linguagem (Tempo)
*   **RNN Simples:** Tentativa de ler código Python.
    *   *Falha:* Problema do Desvanecimento de Gradiente (Vanishing Gradient). A rede esquecia o `def` antes de chegar no `:`. Erro estagnado em 2.5.
*   **LSTM (Long Short-Term Memory):** Implementação de portões lógicos (Input, Forget, Output).
    *   *Sucesso:* Erro caiu para 0.002. A rede decorou a estrutura de função.

## Fase 4: A Singularidade (Neuro-Simbólico)
*   **O Problema da Alucinação:** A rede gerava variáveis inexistentes (`a + b * z`) e loops infinitos.
*   **O Arquiteto Lógico (System 2):** Criação de um Autômato de Pilha para monitorar a saída da LSTM.
    *   *Mecanismo:* Se a LSTM sugere um token inválido (ex: operador após operador), o Arquiteto veta e pede a próxima opção.
*   **Quantização:** Compressão dos pesos para 8-bit. Redução de 350KB para 92KB sem perda significativa de lógica.