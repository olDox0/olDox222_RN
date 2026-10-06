# engine/tools/weight_analyzer.py
""" Analisador de peso do ORN_proj.
Objetivo: identificar libs, modelos e dados que consomem mais espaço/RAM.
Typhon: onde=engine/tools/, oque=análise de peso, quem=weight_analyzer
quando=Fase 6, porquê=otimizar footprint, origem=requirements.txt + models/
consequência=se falhar, revisão manual de dependências. """
import os
import sys
from pathlib import Path
from collections import defaultdict

def analyze_disk_usage(root: Path = Path(".")) -> dict:
    """Analisa uso de disco por diretório e tipo de arquivo."""
    sizes = defaultdict(int)
    file_counts = defaultdict(int)
    
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts or "__pycache__" in path.parts or "venv" in path.parts:
            continue
        
        size = path.stat().st_size
        ext = path.suffix.lower() or "(no ext)"
        
        sizes[ext] += size
        file_counts[ext] += 1
        
        # Agrupar por diretório de topo
        if len(path.parts) > 1:
            top_dir = path.parts[0]
            sizes[f"dir:{top_dir}"] += size
    
    return dict(sizes), dict(file_counts)

def analyze_python_deps() -> dict:
    """Analisa dependências Python instaladas no venv."""
    try:
        import importlib.metadata
        deps = {}
        for dist in importlib.metadata.distributions():
            name = dist.metadata["Name"]
            version = dist.metadata["Version"]
            # Estimar tamanho pelo .dist-info
            size = sum(f.stat().st_size for f in Path(dist._path).rglob("*") if f.is_file())
            deps[name] = {"version": version, "size_bytes": size}
        return deps
    except Exception as e:
        return {"error": str(e)}

def analyze_models(root: Path = Path("models")) -> list:
    """Lista modelos GGUF e seus tamanhos."""
    models = []
    if not root.exists():
        return models
    
    for gguf in root.rglob("*.gguf"):
        size_mb = gguf.stat().st_size / (1024 * 1024)
        models.append({
            "path": str(gguf),
            "size_mb": round(size_mb, 2),
            "name": gguf.name,
        })
    
    return sorted(models, key=lambda x: x["size_mb"], reverse=True)

def format_size(size_bytes: int) -> str:
    """Formata tamanho em bytes para leitura humana."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

if __name__ == "__main__":
    print("=" * 70)
    print(" ANÁLISE DE PESO — ORN_proj ")
    print("=" * 70)
    
    # 1. Uso de disco por extensão
    print("\n[1/4] USO DE DISCO POR EXTENSÃO")
    sizes, counts = analyze_disk_usage()
    for ext, size in sorted(sizes.items(), key=lambda x: x[1], reverse=True)[:10]:
        if not ext.startswith("dir:"):
            print(f"  {ext:12s} {format_size(size):>10s}  ({counts.get(ext, 0)} arquivos)")
    
    # 2. Uso de disco por diretório
    print("\n[2/4] USO DE DISCO POR DIRETÓRIO")
    for key, size in sorted(sizes.items(), key=lambda x: x[1], reverse=True):
        if key.startswith("dir:"):
            dir_name = key[4:]
            print(f"  {dir_name:20s} {format_size(size):>10s}")
    
    # 3. Modelos GGUF
    print("\n[3/4] MODELOS GGUF")
    models = analyze_models()
    if models:
        for m in models:
            print(f"  {m['name']:50s} {m['size_mb']:7.2f} MB")
    else:
        print("  Nenhum modelo encontrado em models/")
    
    # 4. Dependências Python
    print("\n[4/4] DEPENDÊNCIAS PYTHON (Top 15 por tamanho)")
    deps = analyze_python_deps()
    if "error" in deps:
        print(f"  Erro: {deps['error']}")
    else:
        sorted_deps = sorted(deps.items(), key=lambda x: x[1]["size_bytes"], reverse=True)
        for name, info in sorted_deps[:15]:
            print(f"  {name:30s} {info['version']:10s} {format_size(info['size_bytes']):>10s}")
    
    print("\n" + "=" * 70)
