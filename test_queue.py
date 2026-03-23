from engine.runtime.infer_queue import InferQueue

# Criamos uma simulação da Ponte de I.A.
class FakeBridge:
    def ask(self, prompt, **kwargs):
        return f"Eu recebi sua mensagem: {prompt} e estou processando!"

def simular_fila():
    ponte_falsa = FakeBridge()
    # Criamos a fila com a nossa ponte de testes
    fila = InferQueue(bridge=ponte_falsa, max_workers=2)
    
    future = fila.submit("Teste 1")
    
    # Executa a thread de verdade e pega o resultado
    resultado = future.result() 
    print(f"\nRESULTADO DA FILA: {resultado}\n")
    
    fila.shutdown()

if __name__ == "__main__":
    simular_fila()