# alfagold/core/sandbox.py
# [DOX-UNUSED] import os
import shutil
import tempfile
from pathlib import Path

class AegisSandbox:
    """Cria um ambiente efêmero para testar scripts .dox e códigos gerados."""
    def __init__(self, target_file: str):
        self.target_file = Path(target_file)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sicdox_sandbox_"))
        self.sandbox_file = self.temp_dir / self.target_file.name

    def __enter__(self):
        # Clona o arquivo original para a quarentena
        shutil.copy2(self.target_file, self.sandbox_file)
        return self.sandbox_file

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Destrói a quarentena após o teste
        shutil.rmtree(self.temp_dir)

    def validar_sintaxe(self):
        """Roda o 'doxoade check' dentro da quarentena."""
        # Aqui o SiCDox invoca o próprio Auditor Gold em modo silencioso
        from doxoade.commands.check import run_check_logic
        results = run_check_logic(str(self.sandbox_file), fix=False, fast=True, no_cache=True)
        return results.get('summary', {}).get('critical', 0) == 0