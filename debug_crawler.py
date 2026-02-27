import requests
try:
    r = requests.get(
        "https://pt.wikipedia.org/api/rest_v1/page/summary/Python",
        timeout=5,
        headers={"User-Agent": "ORN-Crawler/1.0"}
    )
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}")
    print(f"Primeiros 200 chars: {repr(r.text[:200])}")
    print(f"Tamanho: {len(r.text)} chars")
except Exception as e:
    print(f"Erro: {type(e).__name__}: {e}")