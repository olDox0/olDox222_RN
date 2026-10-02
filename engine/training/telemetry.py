# RAIZ/engine/training/telemetry.py
"""
Telemetria leve para loops de treinamento.
Objetivo: Registrar métricas de desempenho e integridade sem sobrecarregar o sistema.
Typhon: onde=engine/training/, oque=telemetria de treino, quem=telemetry
quando=Fase 3, porquê=monitorar loss/lr/steps, origem=lora_trainer.py
consequência=se falhar, o treino continua mas sem logs (fail-safe).
"""
import json
import time
from pathlib import Path

TELEMETRY_FILE = Path("telemetry/training_run.jsonl")

def log_step(phase: str, message: str) -> None:
    """Log formatado no console com timestamp."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{phase.upper()}] {message}")

def save_metrics(metrics: dict) -> None:
    """Anexa métricas ao arquivo de telemetria de forma segura.
    OSL-15: Falhas de I/O são suprimidas — nunca interrompem o treino.
    """
    try:
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        metrics["timestamp"] = time.time()
        with open(TELEMETRY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[TELEMETRY] Falha ao gravar métricas: {e}")

if __name__ == "__main__":
    # Teste rápido
    log_step("TESTE", "Telemetria operacional")
    save_metrics({"status": "test", "value": 42})
    print(f"[OK] Métricas gravadas em: {TELEMETRY_FILE}")
