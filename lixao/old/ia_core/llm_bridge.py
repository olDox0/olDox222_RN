# ia_core/llm_bridge.py
import os
import sys
import logging
from typing import Optional

class SiCDoxBridge:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from llama_cpp import Llama
            self._engine = Llama(
                model_path=self.model_path,
                n_ctx=1024,        
                n_batch=128,      
                n_threads=2,      # REDUZIDO: Deve ser IGUAL ao número de núcleos físicos.
                verbose=True,     
                n_gpu_layers=0,
                # Adicione estas flags para CPUs sem AVX:
                f16_kv=True,      # Melhora a velocidade do cache
                logits_all=False  # Economiza memória
            )
        return self._engine

    def _load_atlas(self) -> str:
        """Carrega o manual de ferramentas do Doxoade."""
        path = "ia_core/doxoade_atlas.json"
        if os.path.exists(path):
            with open(path, "r", encoding='utf-8') as f:
                atlas = json.load(f)
                return json.dumps(atlas, ensure_ascii=False)
        return "{}"

    def _get_atlas_summary(self):
        """Lê o Atlas gerado para injetar no contexto da IA."""
        import json
        atlas_path = "ia_core/doxoade_atlas.json"
        if os.path.exists(atlas_path):
            with open(atlas_path, "r", encoding="utf-8") as f:
                return json.dumps(json.load(f), ensure_ascii=False)
        return "Nenhum comando mapeado."

    def ask_sicdox(self, user_query: str) -> str:
        engine = self._get_engine()
        
        # ChatML RIGOROSO: Sem espaços extras, formato exato que o Qwen espera.
        # Reduzimos o Atlas no prompt para economizar tokens e evitar confusão.
        prompt = (
            f"<|im_start|>system\nVocê é o SiCDox. Responda apenas com scripts .dox.<|im_end|>\n"
            f"<|im_start|>user\n{user_query}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        
        output = engine(
            prompt,
            max_tokens=256,
            stop=["<|im_end|>", "<|im_start|>", "User:", "#"], # Adicionado '#' como stop para scripts .dox
            temperature=0.1,
            repeat_penalty=1.2 # Aumentado para combater o loop detectado
        )
        
        res = output['choices'][0]['text'].strip()
        # Filtro de limpeza: remove tags que vazaram
        return res.replace("<|im_start|>", "").replace("<|im_end|>", "").strip()

    def shutdown(self):
        """PASC-10: Encerramento explícito para evitar crash de NoneType."""
        if self._engine:
            # Chama o método interno de fechamento da lib antes do Python deletar o objeto
            try:
                self._engine.close()
                self._engine = None
            except:
                pass