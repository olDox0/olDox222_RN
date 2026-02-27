import requests
s = requests.Session()
s.headers["User-Agent"] = "ORN-Crawler/1.0"

# Testa slugs especificos para asyncio
slugs = [
    ("en", "asyncio"),
    ("en", "Asyncio"),
    ("en", "asyncio_(Python)"),
    ("en", "Coroutine"),
    ("en", "Python_concurrency"),
    ("en", "Async/await"),
    ("pt", "Asyncio"),
    ("pt", "Programacao_assincrona"),
]

print("=== Wikipedia slug tests ===")
for lang, slug in slugs:
    import urllib.parse
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(slug)}"
    try:
        r = s.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            print(f"  200 [{lang}] {slug!r:35s} → {d.get('title')!r:.40s}")
        else:
            print(f"  {r.status_code} [{lang}] {slug!r}")
    except Exception as e:
        print(f"  ERR [{lang}] {slug}: {e}")

# Testa Stack Overflow
print("\n=== Stack Overflow test ===")
try:
    r = s.get(
        "https://api.stackexchange.com/2.3/search/advanced",
        params={"q": "asyncio.gather", "site": "stackoverflow",
                "sort": "relevance", "accepted": "True", "pagesize": 1,
                "filter": "!9_bDDxJY5"},
        timeout=10
    )
    data = r.json()
    items = data.get("items", [])
    if items:
        print(f"  OK: {items[0].get('title')!r}")
        print(f"  Quota: {data.get('quota_remaining')}")
    else:
        print(f"  Sem resultados. Quota: {data.get('quota_remaining')}")
except Exception as e:
    print(f"  ERR: {e}")

# Testa PyPI
print("\n=== PyPI test ===")
try:
    r = s.get("https://pypi.org/pypi/asyncio/json", timeout=5)
    if r.status_code == 200:
        d = r.json()
        print(f"  OK: {d['info']['name']} v{d['info']['version']}")
    else:
        print(f"  {r.status_code}")
except Exception as e:
    print(f"  ERR: {e}")