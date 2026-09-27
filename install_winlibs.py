# -*- coding: utf-8 -*-
# install_winlibs.py
"""
ORN — install_winlibs.py
Baixa e instala o toolchain winlibs (MinGW-w64 GCC) automaticamente.
Substitui o antigo w64devkit.

Uso:
    python install_winlibs.py          # Instala na pasta padrão
    python install_winlibs.py --force  # Força reinstalação
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

# OSL-18: stdlib apenas. Zero dependências externas.

DEFAULT_INSTALL_DIR = Path(__file__).parent / "thirdparty" / "winlibs"
GITHUB_API_URL = "https://api.github.com/repos/brechtsanders/winlibs_mingw/releases"

def get_latest_release_url() -> tuple[str, str]:
    """Busca a última release estável do winlibs (x86_64, posix, seh, ucrt, .zip)."""
    print("🔍 Buscando última versão do winlibs no GitHub...")
    req = urllib.request.Request(GITHUB_API_URL, headers={"User-Agent": "ORN-Installer/1.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            releases = json.loads(response.read().decode())
    except Exception as e:
        print(f"❌ Erro ao contatar a API do GitHub: {e}")
        sys.exit(1)

    for rel in releases:
        for asset in rel.get("assets", []):
            name = asset.get("name", "")
            # Queremos x86_64, posix (threads), seh (exceções), ucrt (CRT moderna), .zip
            if (name.endswith(".zip") and 
                "x86_64" in name and 
                "posix" in name and 
                "seh" in name and 
                "ucrt" in name):
                return rel.get("tag_name", "unknown"), asset["browser_download_url"]
                
    print("❌ Nenhuma release compatível (.zip x86_64-posix-seh-ucrt) encontrada.")
    sys.exit(1)

def download_with_progress(url: str, dest_file: Path):
    """Baixa o arquivo mostrando uma barra de progresso simples."""
    req = urllib.request.Request(url, headers={"User-Agent": "ORN-Installer/1.0"})
    with urllib.request.urlopen(req, timeout=600) as response:
        total_size = int(response.info().get('Content-Length', -1))
        downloaded = 0
        block_size = 65536 # 64KB blocks
        with open(dest_file, 'wb') as f:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                f.write(buffer)
                downloaded += len(buffer)
                if total_size > 0:
                    percent = int(downloaded * 100 / total_size)
                    percent = min(100, percent)
                    bar_len = 30
                    filled = int(bar_len * percent / 100)
                    bar = '█' * filled + '-' * (bar_len - filled)
                    sys.stdout.write(f"\r    [{bar}] {percent}% ({downloaded//1048576}MB / {total_size//1048576}MB)")
                    sys.stdout.flush()
        print() # Quebra de linha após o progresso

def download_and_extract(url: str, dest_dir: Path) -> Path:
    """Baixa o arquivo .zip e extrai no diretório de destino."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "winlibs_temp.zip"
    
    print(f"⬇️  Baixando winlibs...")
    try:
        download_with_progress(url, zip_path)
    except Exception as e:
        print(f"\n❌ Erro durante o download: {e}")
        sys.exit(1)
        
    print("📦 Extraindo arquivos (pode levar cerca de 1 minuto)...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
    except Exception as e:
        print(f"❌ Erro ao extrair o ZIP: {e}")
        sys.exit(1)
    finally:
        print("🧹 Limpando arquivo temporário...")
        zip_path.unlink(missing_ok=True)
        
    # O zip do winlibs extrai para uma pasta chamada 'mingw64'
    mingw_dir = dest_dir / "mingw64"
    if not mingw_dir.exists():
        subdirs = [d for d in dest_dir.iterdir() if d.is_dir()]
        mingw_dir = subdirs[0] if subdirs else dest_dir
            
    return mingw_dir

def main():
    parser = argparse.ArgumentParser(description="Instalador automático do winlibs")
    parser.add_argument("--path", type=str, default=str(DEFAULT_INSTALL_DIR))
    parser.add_argument("--force", action="store_true", help="Força reinstalação")
    args = parser.parse_args()
    
    install_dir = Path(args.path)
    mingw_bin = install_dir / "mingw64" / "bin"
    
    if mingw_bin.exists() and not args.force:
        print(f"✅ winlibs já está instalado em:\n    {mingw_bin}")
        return
        
    if args.force and install_dir.exists():
        shutil.rmtree(install_dir, ignore_errors=True)
        
    tag, url = get_latest_release_url()
    print(f"🎯 Versão selecionada: {tag}")
    
    mingw_dir = download_and_extract(url, install_dir)
    mingw_bin = mingw_dir / "bin"
    
    print("\n" + "="*60)
    print("✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!")
    print(f"📁 Binários do GCC estão em: {mingw_bin}")
    print("="*60)

if __name__ == "__main__":
    main()# -*- coding: utf-8 -*-
