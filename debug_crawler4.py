import sys, traceback
sys.path.insert(0, '.')

print("=== Debug search_stackoverflow com withbody filter ===")
try:
    from engine.tools.crawler import search_stackoverflow, _make_session
    sess = _make_session()
    result = search_stackoverflow("asyncio.gather python", session=sess)
    print(f"ok:      {result.ok}")
    print(f"title:   {result.title!r}")
    print(f"error:   {result.error!r}")
    print(f"context: {result.context[:200]!r}")
except Exception as e:
    traceback.print_exc()

print()
print("=== OrnCrawler auto ===")
try:
    from engine.tools.crawler import OrnCrawler
    crawler = OrnCrawler()
    result = crawler.search("asyncio python", source="auto")
    print(f"ok:      {result.ok}")
    print(f"source:  {result.source}")
    print(f"title:   {result.title!r}")
    print(f"context: {result.context[:200]!r}")
except Exception as e:
    traceback.print_exc()