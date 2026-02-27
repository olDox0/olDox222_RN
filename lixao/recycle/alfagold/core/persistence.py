# alfagold/core/persistence.py
import numpy as np
import json
import os
from typing import Dict, Any

"""
Módulo de Persistência Segura (Protocolo Aegis).
Substitui o uso de Pickle por JSON (Estrutura) + NPZ (Tensores).
"""

def save_model_state(path_base: str, params: Dict[str, np.ndarray], config: Dict[str, Any]):
    """
    Salva o estado do modelo de forma segura.
    - params -> .npz (Binário Numérico Otimizado)
    - config -> .json (Metadados Legíveis)
    """
    # 1. Garante diretório
    os.makedirs(os.path.dirname(path_base), exist_ok=True)
    
    # 2. Salva Config/Metadados (JSON)
    json_path = path_base + ".json"
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except TypeError as e:
        raise ValueError(f"Erro ao serializar config para JSON: {e}")

    # 3. Salva Pesos (NPZ)
    npz_path = path_base + ".npz"
    try:
        # np.savez_compressed economiza disco significativamente
        np.savez_compressed(npz_path, **params)
    except Exception as e:
        raise ValueError(f"Erro ao salvar tensores NumPy: {e}")

def load_model_state(path_base: str):
    """
    Carrega o estado do modelo. Retorna (params, config).
    """
    json_path = path_base + ".json"
    npz_path = path_base + ".npz"
    
    if not os.path.exists(json_path) or not os.path.exists(npz_path):
        raise FileNotFoundError(f"Arquivos do modelo não encontrados em: {path_base} (.json/.npz)")
        
    # 1. Carrega Config
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"Arquivo JSON corrompido: {json_path}")
        
    # 2. Carrega Pesos
    try:
        # allow_pickle=False é o padrão do Aegis para segurança
        with np.load(npz_path, allow_pickle=False) as data:
            params = {k: data[k] for k in data.files}
    except Exception as e:
        raise ValueError(f"Erro ao carregar tensores: {e}")
        
    return params, config