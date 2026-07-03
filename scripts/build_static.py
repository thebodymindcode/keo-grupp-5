#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_static.py: статический SEO-слой для SPA keo-grupp-5.

Поисковики не видят hash-роуты (#/u/...), поэтому перед деплоем этот скрипт
парсит данные прямо из index.html (SERVICES, RICH, PRICES, GROUPS) и генерирует
настоящие статические страницы u/<slug>/index.html с полным контентом,
title/description, canonical, JSON-LD (LegalService + Service + FAQPage +
BreadcrumbList), плюс sitemap.xml и robots.txt.

Запуск: python3 scripts/build_static.py   (из папки сайта или откуда угодно)
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent.parent
INDEX = SITE_DIR / "index.html"
BASE_URL = "https://thebodymindcode.github.io/keo-grupp-5/"

PHONE = "+7 (499) 647-75-66"
PHONE_TEL = "+74996477566"
EMAIL = "info@keogroup.ru"
ADDRESS = "Москва, 2-й Южнопортовый проезд, 20А стр. 4"
METRO = "м. Кожуховская"

# ───────────────────────── мини-парсер JS-литералов ─────────────────────────
# Данные в index.html лежат JS-литералами (объекты с ключами без кавычек,
# массивы, строки в двойных кавычках, вызовы S(...)). Регулярки на таком
# ломаются, поэтому маленький рекурсивный парсер нужного подмножества JS.

class JSParser:
    def __init__(self, text):
        self.t = text
        self.i = 0

    def err(self, msg):
        ctx = self.t[max(0, self.i - 40):self.i + 40].replace("\n", "\\n")
        raise SyntaxError(f"{msg} @ {self.i}: ...{ctx}...")

    def ws(self):
        while self.i < len(self.t):
            ch = self.t[self.i]
            if ch in " \t\r\n":
                self.i += 1
            elif self.t.startswith("//", self.i):
                nl = self.t.find("\n", self.i)
                self.i = len(self.t) if nl < 0 else nl
            elif self.t.startswith("/*", self.i):
                end = self.t.find("*/", self.i)
                if end < 0:
                    self.err("незакрытый комментарий")
                self.i = end + 2
            else:
                break

    def peek(self):
        self.ws()
        return self.t[self.i] if self.i < len(self.t) else ""

    def expect(self, ch):
        if self.peek() != ch:
            self.err(f"ожидался {ch!r}")
        self.i += 1

    def string(self):
        quote = self.t[self.i]
        self.i += 1
        out = []
        while self.i < len(self.t):
            ch = self.t[self.i]
            if ch == "\\":
                nxt = self.t[self.i + 1]
                mapped = {"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt)
                out.append(mapped)
                self.i += 2
            elif ch == quote:
                self.i += 1
                return "".join(out)
            else:
                out.append(ch)
                self.i += 1
        self.err("незакрытая строка")

    def ident(self):
        m = re.match(r"[A-Za-z_$][\w$]*", self.t[self.i:])
        if not m:
            self.err("ожидался идентификатор")
        self.i += m.end()
        return m.group(0)

    def value(self):
        ch = self.peek()
        if ch in "\"'":
            return self.string()
        if ch == "[":
            return self.array()
        if ch == "{":
            return self.obj()
        m = re.match(r"-?\d+(?:\.\d+)?", self.t[self.i:])
        if m:
            self.i += m.end()
            txt = m.group(0)
            return float(txt) if "." in txt else int(txt)
        name = self.ident()
        if name == "true":
            return True
        if name == "false":
            return False
        if name == "null":
            return None
        if self.peek() == "(":  # вызов вида S(...) -> список аргументов
            return {"__call__": name, "args": self.args()}
        return {"__ident__": name}

    def args(self):
        self.expect("(")
        vals = []
        while True:
            if self.peek() == ")":
                self.i += 1
                return vals
            vals.append(self.value())
            if self.peek() == ",":
                self.i += 1
            elif self.peek() == ")":
                self.i += 1
                return vals
            else:
                self.err("ожидались , или ) в аргументах")

    def array(self):
        self.expect("[")
        vals = []
        while True:
            if self.peek() == "]":
                self.i += 1
                return vals
            vals.append(self.value())
            if self.peek() == ",":
                self.i += 1
            elif self.peek() == "]":
                self.i += 1
                return vals
            else:
                self.err("ожидались , или ] в массиве")

    def obj(self):
        self.expect("{")
        out = {}
        while True:
            if self.peek() == "}":
                self.i += 1
                return out
            ch = self.peek()
            key = self.string() if ch in "\"'" else self.ident()
            self.expect(":")
            out[key] = self.value()
            if self.peek() == ",":
                self.i += 1
            elif self.peek() == "}":
                self.i += 1
                return out
            else:
                self.err("ожидались , или } в объекте")


def extract_literal(src, marker):
    """Берёт JS-литерал (объект или массив), который начинается сразу после marker."""
    start = src.find(marker)
    if start < 0:
        raise ValueError(f"не найден блок {marker!r} в index.html")
    p = JSParser(src)
    p.i = start + len(marker)
    return p.value()


def load_data():
    src = INDEX.read_text(encoding="utf-8")
    services_raw = extract_literal(src, "const SERVICES=")
    groups_raw = extract_literal(src, "const GROUPS=")
    prices = extract_literal(src, "const PRICES=")
    rich = extract_literal(src, "const RICH=")

    services = []
    for node in services_raw:
        if not (isinstance(node, dict) and node.get("__call__") == "S"):
            continue
        a = node["args"]
        services.append({
            "slug": a[0], "g": a[1], "name": a[2], "note": a[3],
            "body": a[4], "points": a[5],
            "price": a[6] if len(a) > 6 else "",
        })
    groups = {g["key"]: g for g in groups_raw}
    for s in services:
        s["price"] = prices.get(s["slug"]) or s["price"] or "по запросу"
    return services, groups, prices, rich


# ───────────────────────────── HTML-хелперы ─────────────────────────────

def esc(s):
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


CSS = """
:root{--orange:#ef7320;--navy:#1c2430;--muted:#5b6570;--line:#e7e9ee;--bg:#f7f8fa}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Montserrat',Arial,sans-serif;color:var(--navy);background:#fff;line-height:1.6;font-size:16px}
.wrap{max-width:960px;margin:0 auto;padding:0 20px}
header{border-bottom:1px solid var(--line);padding:16px 0}
header .wrap{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.logo{font-weight:800;font-size:19px;letter-spacing:.5px;color:var(--navy);text-decoration:none}
.logo span{color:var(--orange)}
.phone{font-weight:700;color:var(--navy);text-decoration:none;font-size:15px}
main{padding:34px 0 10px}
.crumbs{font-size:13px;color:var(--muted);margin-bottom:18px}
.crumbs a{color:var(--muted)}
.eyebrow{color:var(--orange);font-weight:700;font-size:12px;letter-spacing:1.4px;text-transform:uppercase;margin-bottom:10px}
h1{font-size:clamp(26px,5vw,38px);line-height:1.18;margin-bottom:16px;font-weight:800}
h2{font-size:clamp(20px,3.6vw,26px);margin:38px 0 16px;font-weight:800}
h3{font-size:17px;margin-bottom:6px;font-weight:700}
p.lede{font-size:17.5px;color:var(--muted)}
.upd{font-size:13px;color:var(--muted);margin-top:10px}
.muted{color:var(--muted)}
ul.plain{list-style:none}
ul.plain li{padding:9px 0 9px 26px;position:relative;border-bottom:1px solid var(--line)}
ul.plain li:before{content:"";position:absolute;left:2px;top:17px;width:9px;height:9px;border-radius:3px;background:var(--orange)}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:6px 0}
.card{border:1px solid var(--line);border-radius:14px;padding:18px 20px;background:#fff;box-shadow:0 1px 2px rgba(28,36,48,.04)}
.card b{display:block;margin-bottom:8px;line-height:1.4}
.card p{font-size:14.5px;color:var(--muted)}
.stepn{font-size:26px;font-weight:800;color:var(--orange);margin-bottom:6px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0}
.stats div{flex:1 1 150px;background:var(--bg);border-radius:14px;padding:16px 18px}
.stats b{font-size:22px;display:block;color:var(--orange)}
.stats span{font-size:13px;color:var(--muted)}
.price-line{background:var(--bg);border-left:4px solid var(--orange);border-radius:10px;padding:14px 18px;margin:8px 0;font-weight:700}
.faq{border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:10px}
.faq h3{font-size:15.5px}
.faq p{font-size:14.5px;color:var(--muted)}
.btn{display:inline-block;background:var(--orange);color:#fff;text-decoration:none;font-weight:700;border-radius:10px;padding:13px 26px;margin:8px 0}
.contact{background:var(--bg);border-radius:16px;padding:24px;margin:32px 0}
.contact p{margin:4px 0;font-size:15px}
.rel a{color:var(--navy);font-weight:600}
.rel li:before{background:var(--muted)}
footer{border-top:1px solid var(--line);margin-top:36px;padding:24px 0 34px;font-size:13.5px;color:var(--muted)}
a{color:var(--orange)}
@media(max-width:640px){.cards{grid-template-columns:1fr}}
""".strip()


def head_html(title, desc, canonical, jsonld_blocks):
    ld = "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in jsonld_blocks)
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
{ld}
</head>"""


def jsonld_for(slug, title, desc, faq, price, group_title):
    url = f"{BASE_URL}u/{slug}/"
    legal = {
        "@context": "https://schema.org", "@type": "LegalService",
        "name": "KEO GROUP", "url": BASE_URL,
        "telephone": PHONE_TEL, "email": EMAIL,
        "address": {
            "@type": "PostalAddress", "addressLocality": "Москва",
            "streetAddress": "2-й Южнопортовый проезд, 20А стр. 4",
            "addressCountry": "RU",
        },
        "areaServed": "Москва",
        "openingHours": "Mo-Fr 09:00-18:00",
    }
    service = {
        "@context": "https://schema.org", "@type": "Service",
        "name": title, "description": desc, "url": url,
        "serviceType": group_title,
        "provider": {"@type": "LegalService", "name": "KEO GROUP", "telephone": PHONE_TEL},
        "areaServed": {"@type": "City", "name": "Москва"},
    }
    digits = re.sub(r"\D", "", price or "")
    if digits and "запрос" not in (price or ""):
        service["offers"] = {
            "@type": "AggregateOffer", "priceCurrency": "RUB",
            "lowPrice": digits, "url": url,
        }
    blocks = [legal, service]
    if faq:
        blocks.append({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{
                "@type": "Question", "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            } for q, a in faq],
        })
    blocks.append({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "Услуги", "item": BASE_URL + "#/uslugi"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ],
    })
    return blocks


def page_html(slug, svc, rich_d, services, groups, prices):
    g_key = (rich_d or {}).get("group") or (svc or {}).get("g") or ""
    group = groups.get(g_key, {})
    group_title = group.get("title", "Услуги")
    name = (rich_d or {}).get("title") or (svc or {}).get("name") or slug
    price = prices.get(slug) or (svc or {}).get("price") or "по запросу"

    seo = (rich_d or {}).get("seo") or {}
    title = seo.get("title") or f"{name} в Москве | KEO GROUP"
    lede = (rich_d or {}).get("lede") or (svc or {}).get("body") or (svc or {}).get("note") or ""
    desc = seo.get("desc") or (lede[:157] + "…" if len(lede) > 160 else lede)

    url = f"{BASE_URL}u/{slug}/"
    body = []
    body.append(f'<p class="crumbs"><a href="../../">Главная</a> / <a href="../../#/uslugi">Услуги</a> / {esc(group_title)}</p>')
    body.append(f'<div class="eyebrow">{esc(group_title)}</div>')
    body.append(f"<h1>{esc(name)}</h1>")
    if lede:
        body.append(f'<p class="lede">{esc(lede)}</p>')
    if (rich_d or {}).get("updated"):
        body.append(f'<p class="upd">Обновлено: {esc(rich_d["updated"])}</p>')
    body.append(f'<p class="price-line">Стоимость: {esc(price)}. Точную смету называем после разбора объекта, до старта работ.</p>')
    body.append(f'<a class="btn" href="tel:{PHONE_TEL}">Позвонить: {PHONE}</a>')

    if rich_d:
        if rich_d.get("scenarios"):
            body.append("<h2>Ваша ситуация</h2><div class=\"cards\">")
            for sit, act in rich_d["scenarios"]:
                body.append(f'<div class="card"><b>{esc(sit)}</b><p>Что сделаем: {esc(act)}</p></div>')
            body.append("</div>")
        if rich_d.get("pains"):
            body.append("<h2>Что решаем</h2><ul class=\"plain\">")
            body.extend(f"<li>{esc(x)}</li>" for x in rich_d["pains"])
            body.append("</ul>")
        if rich_d.get("steps"):
            body.append("<h2>Этапы работы</h2><div class=\"cards\">")
            for n, t, dd in rich_d["steps"]:
                body.append(f'<div class="card"><div class="stepn">{esc(n)}</div><b>{esc(t)}</b><p>{esc(dd)}</p></div>')
            body.append("</div>")
        if rich_d.get("stats"):
            body.append("<h2>Результаты направления</h2><div class=\"stats\">")
            for pair in rich_d["stats"]:
                body.append(f"<div><b>{esc(pair[0])}</b><span>{esc(pair[1])}</span></div>")
            body.append("</div>")
        if rich_d.get("tariffs"):
            body.append("<h2>Тарифы и ориентиры</h2><div class=\"cards\">")
            for t in rich_d["tariffs"]:
                tname, tprice, tunit, tdesc = t[0], t[1], t[2], t[3]
                body.append(f'<div class="card"><b>{esc(tname)}: {esc(tprice)} ({esc(tunit)})</b><p>{esc(tdesc)}</p></div>')
            body.append("</div>")
        if rich_d.get("cases"):
            body.append("<h2>Результаты по этой услуге</h2><div class=\"cards\">")
            for obj, res in rich_d["cases"]:
                body.append(f'<div class="card"><b>{esc(obj)}</b><p>{esc(res)}</p></div>')
            body.append("</div>")
        if rich_d.get("micro"):
            body.append(f'<p class="price-line">{esc(rich_d["micro"])}</p>')
    if svc and svc.get("points"):
        body.append("<h2>Что входит</h2><ul class=\"plain\">")
        body.extend(f"<li>{esc(x)}</li>" for x in svc["points"])
        body.append("</ul>")
    if svc and svc.get("body") and svc["body"] != lede:
        body.append(f'<p class="muted" style="margin-top:14px">{esc(svc["body"])}</p>')

    faq = (rich_d or {}).get("faq") or []
    if faq:
        body.append("<h2>Частые вопросы</h2>")
        for q, a in faq:
            body.append(f'<div class="faq"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>')

    # контакты
    body.append(f"""<div class="contact"><h2 style="margin-top:0">Контакты KEO GROUP</h2>
<p>Телефон: <a href="tel:{PHONE_TEL}">{PHONE}</a> (будни с 9 до 18)</p>
<p>Почта: <a href="mailto:{EMAIL}">{EMAIL}</a></p>
<p>Адрес: {esc(ADDRESS)}, {esc(METRO)}</p>
<a class="btn" href="../../#/u/{slug}">Открыть полную версию страницы</a></div>""")

    # смежные услуги той же группы, обычные ссылки на статические страницы
    rel = [s for s in services if s["g"] == g_key and s["slug"] != slug][:4]
    if rel:
        body.append('<h2>Смежные услуги</h2><ul class="plain rel">')
        for r in rel:
            body.append(f'<li><a href="../{r["slug"]}/">{esc(r["name"])}</a> <span class="muted">{esc(r["note"])}</span></li>')
        body.append("</ul>")

    jsonld = jsonld_for(slug, name, desc, faq, price, group_title)
    return f"""{head_html(title, desc, url, jsonld)}
<body>
<header><div class="wrap"><a class="logo" href="../../">KEO <span>GROUP</span></a><a class="phone" href="tel:{PHONE_TEL}">{PHONE}</a></div></header>
<main><div class="wrap">
{chr(10).join(body)}
</div></main>
<footer><div class="wrap"><p>KEO GROUP, юридическое и градостроительное сопровождение коммерческой недвижимости в Москве.</p>
<p>{esc(ADDRESS)}, {esc(METRO)}. Телефон: {PHONE}. Почта: {EMAIL}.</p>
<p><a href="../../">На главную</a> · <a href="../../#/u/{slug}">Полная версия этой страницы</a></p></div></footer>
</body>
</html>
"""


def main():
    services, groups, prices, rich = load_data()
    svc_by_slug = {s["slug"]: s for s in services}
    slugs = list(dict.fromkeys([s["slug"] for s in services] + list(rich.keys())))

    made = []
    for slug in slugs:
        html = page_html(slug, svc_by_slug.get(slug), rich.get(slug), services, groups, prices)
        out = SITE_DIR / "u" / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        made.append(slug)

    today = date.today().isoformat()
    urls = [BASE_URL] + [f"{BASE_URL}u/{s}/" for s in made]
    items = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq></url>"
        for u in urls)
    (SITE_DIR / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n</urlset>\n", encoding="utf-8")
    (SITE_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}sitemap.xml\n", encoding="utf-8")

    print(f"Готово: {len(made)} статических страниц в u/, sitemap.xml ({len(urls)} URL), robots.txt")
    rich_n = sum(1 for s in made if s in rich)
    print(f"Из них по RICH-данным: {rich_n}, по базовым SERVICES: {len(made) - rich_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
