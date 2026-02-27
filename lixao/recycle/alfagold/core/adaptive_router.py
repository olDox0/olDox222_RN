# alfagold/core/adaptive_router.py
import numpy as np
# [DOX-UNUSED] from .math_utils import softmax

class AdaptiveRouter:
    """
    Roteador Adaptativo v2.0 (Vectorized & Stable).
    - Evita Cluster Collapse com inicialização baseada em dados.
    - Usa álgebra linear otimizada para cálculo de distância.
    """
    def __init__(self, d_model, num_clusters=4):
        self.d_model = d_model
        self.num_clusters = num_clusters
        
        # Inicializa como Zero para indicar que precisa de 'Warm Start'
        self.centroids = np.zeros((num_clusters, d_model), dtype=np.float32)
        self.initialized = False
        
        # Contadores com decaimento (Moving Average)
        self.counts = np.ones(num_clusters, dtype=np.float32)
        
        # Camada de projeção linear (Gate)
        self.W_gate = np.random.randn(d_model, num_clusters).astype(np.float32) * 0.05

    def _warm_start(self, batch_vectors):
        """Inicialização K-Means++ simplificada: pega amostras reais como centroides."""
        n = batch_vectors.shape[0]
        # Se n < clusters, replace=True (repete dados). Se n >= clusters, replace=False (pega únicos).
        indices = np.random.choice(n, self.num_clusters, replace=(n < self.num_clusters))
        self.centroids = batch_vectors[indices].copy()
        self.initialized = True
        print("   🧠 [Router] Centroides inicializados com dados reais.")

    def route(self, state_vector, training=True, lr=0.1):
        """
        Roteamento Vetorizado.
        Aceita input (Batch, D) ou (D,).
        """
        # Garante shape 2D (Batch, D)
        if state_vector.ndim == 1:
            state_vector = state_vector[np.newaxis, :]
            
        # Warm Start na primeira execução
        if training and not self.initialized:
            self._warm_start(state_vector)
            
        # 1. Distância Euclidiana Vetorizada
        # (x-c)^2 = x^2 + c^2 - 2xc
        # Essa forma usa BLAS (Matrix Multiplication) que é muito mais rápida que loops
        
        # x^2 (Batch, 1)
        x2 = np.sum(state_vector**2, axis=1, keepdims=True)
        # c^2 (1, Clusters)
        c2 = np.sum(self.centroids**2, axis=1)
        # 2xc (Batch, Clusters)
        xc = np.dot(state_vector, self.centroids.T)
        
        # Distância Quadrada
        dists = x2 + c2 - 2 * xc
        # Correção numérica (pode dar negativo pequeno por erro de float)
        dists = np.maximum(dists, 0.0)
        
        # 2. Hard Assignment
        labels = np.argmin(dists, axis=1)
        
        # 3. Online Update (Apenas em treino)
        if training:
            # Vetorização do update dos centroides
            # Em vez de loop Python, usamos indexação avançada se possível,
            # mas para updates esparsos (poucos clusters vencedores), o loop é aceitável
            # se o batch for pequeno. Para batches grandes, a média é melhor.
            
            for i, label in enumerate(labels):
                # Learning Rate Decaído (1/N)
                count = self.counts[label]
                alpha = lr / (1.0 + count * 0.01) # Decaimento mais suave
                
                # Move centroide: c = c + alpha * (x - c)
                diff = state_vector[i] - self.centroids[label]
                self.centroids[label] += alpha * diff
                self.counts[label] += 1
                
            # Revival de Clusters Mortos (Otimização Genética)
            # Se um cluster tem contagem muito baixa comparada à média, reinicia
            mean_count = np.mean(self.counts)
            dead_clusters = np.where(self.counts < mean_count * 0.01)[0]
            
            if len(dead_clusters) > 0 and len(labels) > 0:
                # Reinicia centroide morto para a posição do dado atual (dá uma nova chance)
                victim_idx = np.random.randint(len(state_vector))
                for dc in dead_clusters:
                    self.centroids[dc] = state_vector[victim_idx] + np.random.randn(self.d_model)*0.01
                    self.counts[dc] = mean_count * 0.1 # Reset parcial

        # 4. Soft Gating (Kernel RBF)
        # Scores = exp(-gamma * dist)
        # Gamma ajustável dinamicamente poderia ser interessante
        scores = np.exp(-1.0 * dists)
        
        # Normaliza (Softmax das distâncias)
        # axis=1 para somar sobre os clusters
        denominator = np.sum(scores, axis=1, keepdims=True) + 1e-9
        weights = scores / denominator
        
        return labels, weights

    def get_state(self):
        return {'centroids': self.centroids, 'counts': self.counts, 'W_gate': self.W_gate}

    def set_state(self, state):
        self.centroids = state['centroids']
        self.counts = state['counts']
        if 'W_gate' in state: self.W_gate = state['W_gate']
        self.initialized = True