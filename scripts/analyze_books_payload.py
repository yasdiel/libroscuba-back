import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "_books_response.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

raw = open(path, "rb").read()
print("books:", len(data))
print("json_bytes:", len(raw))
for i, b in enumerate(data[:5]):
    url = b.get("foto_url") or ""
    print(f"  [{i}] {b.get('titulo', '')[:50]!r} foto_url_len={len(url)} data_url={url.startswith('data:')}")
