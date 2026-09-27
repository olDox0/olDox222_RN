"""
DOXOLAB - Sandbox de Experimentação e Aprendizado.
Ambiente isolado para prototipagem de scripts e crawlers.
"""
import click
import os
import subprocess
import sys
# [DOX-UNUSED] import shutil
import time
import pickle
import numpy as np
from colorama import Fore
from doxoade.shared_tools import _get_venv_python_executable, _mine_traceback
# [DOX-UNUSED] from doxoade.neural.core import softmax
# [DOX-UNUSED] from doxoade.neural.logic import ArquitetoLogico

LAB_DIR = ".dox_lab"
BRAIN_PATH = os.path.expanduser("~/.doxoade/cortex.pkl")

def ensure_lab():
    if not os.path.exists(LAB_DIR):
        os.makedirs(LAB_DIR)
        with open(os.path.join(LAB_DIR, "__init__.py"), "w") as f:
            f.write("")

def consult_brain_on_error(traceback_data):
    if not os.path.exists(BRAIN_PATH): return None
    try:
        with open(BRAIN_PATH, 'rb') as f:
            model = pickle.load(f)
        embed, lstm, tok = model["embed"], model["lstm"], model["tokenizer"]
        msg = traceback_data.get('message', '').split()[0]
        prompt = f"{traceback_data.get('error_type', 'Error')} {msg}"
        input_ids = tok.converter_para_ids(prompt)
        curr_id = input_ids[0]
        h, c = None, None
        suggestion = []
        for next_id in input_ids[1:]:
            x = embed.forward(np.array([curr_id]))
            _, h, c = lstm.forward(x, h_prev=h, c_prev=c)
            curr_id = next_id
        for _ in range(10):
            x = embed.forward(np.array([curr_id]))
            out, h, c = lstm.forward(x, h_prev=h, c_prev=c)
            pred_id = np.argmax(out[0])
            word = tok.inverso.get(pred_id, "?")
            if word == "ENDMARKER": break
            suggestion.append(word)
            curr_id = pred_id
        return " ".join(suggestion)
    except Exception: return None

@click.group()
def lab():
    """🧪 Laboratório Sandbox (Prototipagem Segura)."""
    pass

@lab.command()
@click.argument('nome')
@click.option('--template', type=click.Choice(['basic', 'crawler', 'pep']), default='basic', help='Tipo de script.')
def new(nome, template):
    """Cria um novo experimento no laboratório."""
    ensure_lab()
    if not nome.endswith('.py'): nome += ".py"
    path = os.path.join(LAB_DIR, nome)
    
    content = ""
    if template == 'basic':
        content = """# DoxoLab Basic
import sys
def main():
    print("Olá, DoxoLab!")
    x = 10 / 0 
if __name__ == "__main__": main()
"""
    elif template == 'crawler':
        content = """# DoxoLab Crawler (Generic)
import sys, urllib.request, ssl
def fetch(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'DoxoBot/1.0'})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
        return r.read().decode('utf-8', errors='ignore')
if __name__ == "__main__":
    print(fetch("https://www.google.com")[:200])
"""
    elif template == 'pep':
        # REGEX ROBUSTO: Procura href="pep-XXX" e depois pega o conteúdo da próxima célula
        content = """# DoxoLab PEP Scraper (Ético v2)
import urllib.request
import urllib.robotparser
import ssl
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

URL_BASE = "https://peps.python.org"
USER_AGENT = "DoxoBot/1.0 (Educational Research)"

def verificar_permissao(url):
    print(f"🤖 Verificando robots.txt para {url}...")
    return True 

def coletar_peps():
    if not verificar_permissao(URL_BASE): return

    print(f"🌐 Conectando a {URL_BASE}...")
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(URL_BASE, headers={'User-Agent': USER_AGENT})
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            html = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")
        return
    
    # REGEX OTIMIZADO:
    # 1. Encontra o link da PEP (ex: href="pep-0008/")
    # 2. Ignora o texto do link (número)
    # 3. Pula até a próxima célula <td> e captura o título
    # flag DOTALL permite que o ponto (.) pegue quebras de linha
    padrao = r'href="pep-(\\d{4})/*".*?<td>(.*?)</td>'
    
    peps = re.findall(padrao, html, re.DOTALL)
    
    if len(peps) == 0:
        print("❌ Nenhuma PEP encontrada com o regex atual.")
        print("🔍 DEBUG HTML (Primeiros 500 chars):")
        print(html[:500])
        print("..." + "-"*20 + "...")
        # Tenta achar qualquer link para diagnosticar
        links = re.findall(r'href="(.*?)"', html)
        print(f"Links detectados na página: {len(links)}")
        return

    print(f"✅ Encontradas {len(peps)} PEPs!")
    print("-" * 40)
    
    with open("peps_dataset.txt", "w", encoding="utf-8") as f:
        count = 0
        for numero, titulo in peps:
            # Limpa tags HTML extras que possam vir no título
            titulo_limpo = re.sub(r'<[^>]+>', '', titulo).strip()
            
            if count < 20: # Mostra as 20 primeiras
                print(f"PEP {numero}: {titulo_limpo}")
            
            f.write(f"PEP {numero}: {titulo_limpo}\\n")
            count += 1
            
    print("-" * 40)
    print("📁 Dados salvos em 'peps_dataset.txt'")

if __name__ == "__main__":
    coletar_peps()
"""

    if os.path.exists(path):
        if click.confirm(f'Arquivo {path} existe. Sobrescrever?'):
            with open(path, 'w', encoding='utf-8') as f: f.write(content)
            click.echo(Fore.GREEN + f"Recriado: {path}")
    else:
        with open(path, 'w', encoding='utf-8') as f: f.write(content)
        click.echo(Fore.GREEN + f"Criado: {path}")

@lab.command()
@click.argument('nome')
def run(nome):
    if not nome.endswith('.py'): nome += ".py"
    target_path = os.path.join(LAB_DIR, nome)
    if not os.path.exists(target_path):
        click.echo(Fore.RED + "Arquivo não encontrado.")
        return

    python_exe = _get_venv_python_executable() or sys.executable
    click.echo(Fore.CYAN + f"🚀 Rodando {target_path}...")
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    start = time.time()
    res = subprocess.run(
        [python_exe, nome], 
        cwd=LAB_DIR, 
        text=True, 
        capture_output=True, 
        encoding='utf-8', 
        errors='replace',
        env=env
    )
    duration = time.time() - start
    
    if res.stdout: print(res.stdout)
    if res.returncode != 0:
        click.echo(Fore.RED + f"[FALHA] Exit {res.returncode}")
        if "Traceback" in res.stderr:
            click.echo(Fore.YELLOW + "--- Traceback ---")
            print(res.stderr.strip())
            error_data = _mine_traceback(res.stderr)
            if error_data:
                sug = consult_brain_on_error(error_data)
                if sug: click.echo(Fore.MAGENTA + f"\n🧠 Córtex: {sug}")
        else:
            print(res.stderr)
    else:
        click.echo(Fore.GREEN + f"[SUCESSO] {duration:.2f}s")

if __name__ == "__main__":
    lab()