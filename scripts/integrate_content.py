#!/usr/bin/env python3
"""Вливает JSON-контент лендингов из _content/ в объект RICH внутри index.html.

Каждый _content/<slug>.json (структура RICH v2 + служебные slug/img_prompt/sources)
превращается в запись RICH[slug]. Служебные поля отбрасываются, img ставится = slug
(hero берёт ./images/land/<slug>.jpg). Существующая запись с тем же slug заменяется.
Запуск: python3 scripts/integrate_content.py [--dry]
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDX = ROOT / "index.html"
CONTENT = ROOT / "_content"
FIELDS = ["group","title","lede","ledePoints","badge","img","updated","scenarios","pains","steps",
          "stats","tariffs","cases","micro","faq","seo"]

def js(v):
    return json.dumps(v, ensure_ascii=False)

def entry_js(d, slug):
    d = dict(d); d.setdefault("img", slug)
    parts = []
    for k in FIELDS:
        if k in d and d[k] is not None:
            parts.append(f'{k}:{js(d[k])}')
    return '"%s":{%s}' % (slug, ",".join(parts))

def main():
    dry = "--dry" in sys.argv
    html = IDX.read_text(encoding="utf-8")
    m = re.search(r'const RICH=\{', html)
    if not m: sys.exit("RICH не найден")
    # найти конец объекта RICH: сбалансированные скобки от m.end()-1
    i = m.end() - 1; depth = 0
    while True:
        c = html[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: break
        i += 1
    body_start, body_end = m.end(), i  # содержимое между { }
    body = html[body_start:body_end]

    added, replaced = [], []
    for f in sorted(CONTENT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        slug = d.get("slug") or f.stem
        for extra in ("slug","img_prompt","sources"): d.pop(extra, None)
        ent = entry_js(d, slug)
        # уже есть? запись начинается с  slug": или slug: (в старом стиле ключи без кавычек)
        pat = re.compile(r'(,?\n?)\s*"?' + re.escape(slug) + r'"?\s*:\s*\{')
        mm = pat.search(body)
        if mm:
            # найти конец этой записи (сбалансированные скобки)
            j = body.index('{', mm.start()); depth = 0; k = j
            while True:
                if body[k] == '{': depth += 1
                elif body[k] == '}':
                    depth -= 1
                    if depth == 0: break
                k += 1
            body = body[:mm.start()] + mm.group(1) + "\n " + ent + body[k+1:]
            replaced.append(slug)
        else:
            sep = "," if body.strip() else ""
            body = body.rstrip() + sep + "\n " + ent + "\n"
            added.append(slug)

    new_html = html[:body_start] + body + html[body_end:]
    print(f"добавлено: {len(added)} {added}")
    print(f"заменено: {len(replaced)} {replaced}")
    if dry:
        print("dry-run, файл не тронут"); return
    IDX.write_text(new_html, encoding="utf-8")
    print("index.html обновлён. Не забудь: cp index.html 404.html && python3 scripts/build_static.py")

if __name__ == "__main__":
    main()
