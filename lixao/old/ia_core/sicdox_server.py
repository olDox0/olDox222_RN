# ia_core/sicdox_server.py
from flask import Flask, request, jsonify
from .llm_bridge import SiCDoxBridge
import logging

app = Flask(__name__)
# O modelo carrega AQUI, uma única vez.
bridge = SiCDoxBridge("models/sicdox/Qwen2.5-Coder-0.5B-Instruct-Q4_K_M-GGUF/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf")

@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    goal = data.get('goal', '')
    # System 1 + System 2 Workflow
    proposal = bridge.ask_sicdox(goal)
    return jsonify({"plan": proposal})

if __name__ == '__main__':
    print("🧠 SiCDox Server: Aguardando ordens na porta 5000...")
    app.run(port=5000, threaded=False) # Threaded=False para não brigar com a CPU