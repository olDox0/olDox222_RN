# ORN — olDox222 Rede Neural

ORN é uma Interface de Linha de Comando de Inteligência Artificial (AI CLI) desenvolvida do zero para operar como um assistente de código local, rodando sobre hardware com **alta restrição de recursos**. 

Projetado especificamente para rodar o modelo **Qwen2.5-Coder-0.5B-Instruct (GGUF)** de forma viável em processadores legados de baixa potência (ex: **Intel Celeron N2808**, 2 threads, sem AVX).

## 🚀 Funcionalidades

* **Iniciativa Llama-cpp Otimizada:** Pipeline de compilação C/C++ personalizado desativando instruções modernas não suportadas e forçando compilação `SSE4.1/SSE4.2`.
* **Vulcan Optimizer (`doxoade vulcan`):** Um compilador/otimizador proprietário integrado que varre dependências do Python (como o *binding* do `llama_cpp`), remove docstrings, minifica variáveis e converte código `.py` em binários `.pyd` compilados com SIMD, economizando memória RAM e ciclos de CPU.
* **ORN Brain:** Sistema telemétrico interno que monitora o uso de tokens, tempos de predição, cargas de CPU, RAM e histórico de rascunhos (*drafts*).
* **Gestão de Contexto Agressiva:** Buffer contínuo de 384 tokens e métricas precisas desenhadas para não estourar a RAM limitada do sistema.

## 🛠️ Requisitos de Sistema

* **OS:** Windows
* **CPU:** Intel Celeron N2808 (Arquitetura Silvermont) ou superior.
* **RAM:** Uso estimado de 430MB a 450MB em tempo de inferência.
* **Python:** 3.10+ (Homologado em 3.12.4).
* **Compilador:** `w64devkit` (GCC/G++) acessível no PATH para compilações locais.

## 📦 Instalação

1. Clone o repositório e crie o seu ambiente virtual:
   ```cmd
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. Instale os pacotes base (menos o engine LLM):
   ```cmd
   pip install -r requirements.txt
   pip install -e .
   ```

3. Verifique o ambiente e compile o `llama-cpp-python` nativamente:
   O script `install.py` aplicará automaticamente as flags compatíveis com o Celeron N2808 (desativando BLAS e OpenMP, focando em SSE).
   ```cmd
   python install.py --recompile
   ```

4. Valide a instalação:
   ```cmd
   python install.py --check
   orn config --show
   ```

## 🧠 Uso (CLI)

Pergunte diretamente à Rede Neural através do comando `think`:

```cmd
orn think "faça buffer python" --raw --telemetry
```

Para inspecionar a velocidade de processamento, telemetria em tempo real e uso de RAM, acesse o painel *brain*:
```cmd
orn brain --json-output -n 2
```

Saiba mais em:
```cmd
orn --help
orn tutorial
```

---