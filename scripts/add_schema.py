#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Микроразметка Schema.org для страниц keogroup.ru: FAQPage и BreadcrumbList.

Зачем: в Яндексе такой сниппет занимает больше места и собирает больше кликов.
На 20.07.2026 сайт получал 901 показ по рабочим запросам и всего 23 клика при позициях 5-10,
то есть нас видели и проходили мимо. Разметка это первый и самый дешёвый рычаг.

Берёт готовый контент со страницы, ничего не выдумывает:
  вопросы и ответы  <details class="faq"><summary>вопрос</summary><p>ответ</p></details>
  крошки            <p class="crumbs"><a href="/">Главная</a> / ... <span>Текущая</span></p>
Идемпотентен: помечает вставку комментарием и при повторном запуске переписывает её, не плодя дубли.
"""
import pathlib, re, json, html, sys

ROOT = pathlib.Path.home()/".business/sites/out/keo-grupp-5/_mpsite"
SITE = "https://keogroup.ru"
MARK_S, MARK_E = "<!-- schema:auto -->", "<!-- /schema:auto -->"

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def faq_blocks(h):
    out = []
    for m in re.finditer(r"<details[^>]*class=\"[^\"]*faq[^\"]*\"[^>]*>(.*?)</details>", h, re.S):
        block = m.group(1)
        q = re.search(r"<summary[^>]*>(.*?)</summary>", block, re.S)
        if not q: continue
        a = clean(block[q.end():])
        qt = clean(q.group(1))
        if qt and a and len(a) > 20:
            out.append((qt, a[:900]))
    return out

def crumbs(h, url):
    m = re.search(r"class=\"crumbs\"[^>]*>(.*?)</p>", h, re.S)
    if not m: return []
    items, pos = [], 1
    for a in re.finditer(r"<a href=\"([^\"]+)\"[^>]*>(.*?)</a>", m.group(1), re.S):
        href, name = a.group(1), clean(a.group(2))
        if not name: continue
        items.append({"@type": "ListItem", "position": pos,
                      "name": name, "item": SITE + href if href.startswith("/") else href})
        pos += 1
    last = re.search(r"<span[^>]*>(.*?)</span>", m.group(1), re.S)
    if last and clean(last.group(1)):
        items.append({"@type": "ListItem", "position": pos,
                      "name": clean(last.group(1)), "item": SITE + url})
    return items

def build(h, url):
    graph = []
    fq = faq_blocks(h)
    if len(fq) >= 2:
        graph.append({"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in fq]})
    cr = crumbs(h, url)
    if len(cr) >= 2:
        graph.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                      "itemListElement": cr})
    if not graph: return None
    return "\n".join(MARK_S and [MARK_S] + [
        '<script type="application/ld+json">' + json.dumps(g, ensure_ascii=False) + "</script>"
        for g in graph] + [MARK_E])

def main():
    files = sorted(ROOT.rglob("index.html"))
    done = faq_n = bc_n = 0
    for f in files:
        h = f.read_text(encoding="utf-8")
        url = "/" + str(f.parent.relative_to(ROOT)).replace("\\", "/").strip(".") + "/"
        url = url.replace("//", "/")
        if url == "/./" or url == "//": url = "/"
        # снять прошлую вставку
        h_clean = re.sub(re.escape(MARK_S) + r".*?" + re.escape(MARK_E), "", h, flags=re.S)
        block = build(h_clean, url)
        if not block:
            if h != h_clean: f.write_text(h_clean, encoding="utf-8")
            continue
        if "</head>" not in h_clean: continue
        new = h_clean.replace("</head>", block + "\n</head>", 1)
        if new != h:
            f.write_text(new, encoding="utf-8"); done += 1
        if "FAQPage" in block: faq_n += 1
        if "BreadcrumbList" in block: bc_n += 1
    print(f"страниц обработано: {len(files)} | размечено: {done}")
    print(f"  FAQPage: {faq_n} | BreadcrumbList: {bc_n}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
