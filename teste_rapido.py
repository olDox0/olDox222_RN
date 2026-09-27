import time
from engine.tools.server_client import query

print("Enviando requisição 1 (Vai carregar o System Prompt no Cache)...")
t0 = time.perf_counter()
resp1 = query("Conte ate 3.", max_tokens=10)
print(f"Resp 1: {resp1['output']} | Tempo: {time.perf_counter() - t0:.2f}s")

print("\nEnviando requisição 2 (O C vai pular o processamento do System Prompt!)...")
t0 = time.perf_counter()
resp2 = query("Conte ate 5.", max_tokens=10)
print(f"Resp 2: {resp2['output']} | Tempo: {time.perf_counter() - t0:.2f}s")