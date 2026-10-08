# patch_httplib.py
from pathlib import Path
import re

target = Path("thirdparty/llama.cpp/vendor/cpp-httplib/httplib.h")
if not target.exists():
    print(f"❌ Não encontrado: {target.resolve()}")
    exit(1)

content = target.read_text(encoding="utf-8", errors="ignore")

# 1. Neutraliza o #error que bloqueia a compilação
content = re.sub(
    r'#error\s*\\?\s*["\']cpp-httplib doesn\'t support Windows 8 or lower[^"\']*["\']',
    '// check desativado para MinGW',
    content
)

# 2. Injeta _WIN32_WINNT 0x0A00 (Windows 10/11) no topo
inject = "#ifndef _WIN32_WINNT\n#define _WIN32_WINNT 0x0A00\n#elif _WIN32_WINNT < 0x0A00\n#undef _WIN32_WINNT\n#define _WIN32_WINNT 0x0A00\n#endif\n"
if "_WIN32_WINNT 0x0A00" not in content:
    content = inject + content

target.write_text(content, encoding="utf-8")
print("✔ httplib.h corrigido com sucesso!")
