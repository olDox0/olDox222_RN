import sys
print(f"Python: {sys.executable}\n")

import requests
print(f"[OK] requests {requests.__version__}")
try:
    from bs4 import BeautifulSoup
    print("[OK] beautifulsoup4")
except: print("[AVISO] beautifulsoup4 ausente")

print("\n=== Teste Wikipedia — slug variants ===")
for slug in ["Asyncio", "asyncio", "Python_(programming_language)"]:
    try:
        r = requests.get(
            f"https://pt.wikipedia.org/api/rest_v1/page/summary/{slug}",
            timeout=5, headers={"User-Agent": "ORN-Crawler/1.0"}
        )
        if r.status_code == 200:
            print(f"  OK  {slug} → {r.json().get('title')}")
        else:
            print(f"  {r.status_code} {slug}")
    except Exception as e:
        print(f"  ERR {slug}: {e}")

print("\n=== Teste OrnCrawler ===")
try:
    from engine.tools.crawler import OrnCrawler
    crawler = OrnCrawler()
    for q, src in [("asyncio", "wikipedia"), ("asyncio python", "auto")]:
        result = crawler.search(q, source=src)
        print(f"  [{src}] {q!r}")
        print(f"    ok={result.ok}  title={result.title!r}")
        if not result.ok: print(f"    error={result.error}")
        else: print(f"    context={result.context[:80]!r}")
except Exception as e:
    import traceback; traceback.print_exc()