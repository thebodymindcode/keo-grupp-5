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
BASE_URL = "https://keogroup.ru/"

PHONE = "+7 (499) 647-75-66"
PHONE_TEL = "+74996477566"
EMAIL = "info@keogroup.ru"
ADDRESS = "Москва, 2-й Южнопортовый проезд, 20А стр. 4"
METRO = "м. Кожуховская"
TELEGRAM = "keogroup"  # username Telegram (уточнить у владельца, поставить точный)

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
:root{--orange:#ef7320;--orange2:#d8620f;--navy:#1c2430;--muted:#5b6570;--line:#e7e9ee;--bg:#f7f8fa;--soft:#f2f4f7;--ink3:#9aa0b4}
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
/* ===== ВЕРХНЕЕ МЕНЮ ===== */
.mainnav{border-bottom:1px solid var(--line);background:#fff;position:sticky;top:0;z-index:50}
.navwrap{display:flex;align-items:center;gap:18px;padding:12px 0}
.mainnav .logo{font-weight:800;font-size:19px;color:var(--navy);text-decoration:none}
.mainnav .logo span{color:var(--orange)}
.navlinks{display:flex;gap:20px;flex:1;flex-wrap:wrap}
.navlinks a{color:var(--navy);text-decoration:none;font-weight:600;font-size:15px}
.navlinks a:hover{color:var(--orange)}
.navphone{color:var(--navy);font-weight:800;text-decoration:none;font-size:16px;white-space:nowrap}
@media(max-width:860px){
  .mainnav{position:static}
  .navwrap{padding:12px 18px;gap:10px;justify-content:space-between}
  .navlinks{display:none}
  .mainnav .logo{font-size:17px}
  .navphone{font-size:15px}
}
/* ===== СТАТЬЯ-ЛОНГРИД ===== */
.article{max-width:820px}
/* HERO с картинкой */
.ahero{border-radius:20px;overflow:hidden;background-size:cover;background-position:center;margin:8px 0 22px;min-height:340px;display:flex;align-items:flex-end}
.ahero-in{padding:26px 30px;color:#fff;width:100%}
.ahero .crumbs.light{color:rgba(255,255,255,.85);font-size:13px;margin:0 0 10px}
.ahero .crumbs.light a{color:#fff}
.ahero .eyebrow.light{color:#ffb877;font-weight:800;font-size:13px;letter-spacing:.04em;text-transform:uppercase;margin-bottom:8px}
.ahero h1{font-size:36px;line-height:1.12;margin:0;color:#fff;text-shadow:0 2px 20px rgba(0,0,0,.3)}
.article .lede{font-size:18.5px;line-height:1.6;color:#333;margin:0 0 18px}
/* КАРТОЧКИ КЛЮЧЕВЫХ ФАКТОВ */
.statcards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0 6px}
.statcard{background:linear-gradient(160deg,#fff,#fbf7f2);border:1px solid var(--line);border-radius:16px;padding:16px 16px 15px;box-shadow:0 4px 16px rgba(40,38,44,.05)}
.statcard b{display:block;font-size:24px;font-weight:800;color:var(--orange);line-height:1.05;margin-bottom:6px}
.statcard span{font-size:12.5px;color:#555;line-height:1.4}
@media(max-width:720px){.statcards{grid-template-columns:1fr 1fr}.ahero h1{font-size:26px}.ahero{min-height:250px}}
.toc{background:var(--soft);border:1px solid var(--line);border-radius:14px;padding:16px 20px;margin:22px 0}
.toc-t{font-weight:800;font-size:14px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);margin-bottom:8px}
.toc ol{margin:0;padding-left:20px}.toc li{padding:4px 0;font-size:15.5px}
.toc a{color:var(--navy);text-decoration:none;border-bottom:1px solid transparent}
.toc a:hover{color:var(--orange);border-bottom-color:var(--orange)}
.asec{margin:30px 0}
.asec h2{font-size:25px;line-height:1.2;margin:34px 0 14px;scroll-margin-top:80px}
.asec h3{font-size:19px;margin:22px 0 10px}
.asec p{font-size:16.5px;line-height:1.7;margin:0 0 14px;color:#26262b}
.asec ul,.asec ol{margin:0 0 16px;padding-left:24px}
.asec li{font-size:16.5px;line-height:1.65;margin-bottom:7px}
.asec table{width:100%;border-collapse:collapse;margin:18px 0;font-size:15px;box-shadow:0 3px 14px rgba(40,38,44,.05);border-radius:10px;overflow:hidden}
.asec th,.asec td{border-bottom:1px solid var(--line);padding:11px 14px;text-align:left;vertical-align:top}
.asec thead th{background:var(--navy);color:#fff;font-weight:700;border:0}
.asec tbody tr:nth-child(even){background:var(--soft)}
.asec td:first-child{font-weight:600;color:var(--navy)}
/* АКЦЕНТЫ в тексте */
.asec strong,.asec b{color:var(--orange2);font-weight:700}
.asec mark{background:linear-gradient(180deg,transparent 55%,#ffe0b8 55%);color:inherit;padding:0 1px;font-weight:600}
.asec ul li::marker{color:var(--orange)}
.asec ol li::marker{color:var(--orange);font-weight:700}
/* ВРЕЗКИ (важно / на заметку / совет) */
.callout{border-radius:14px;padding:15px 18px 15px 20px;margin:20px 0;font-size:16px;line-height:1.6;border-left:4px solid var(--orange);background:#fff7ef}
.callout .cl-t{display:block;font-weight:800;font-size:13px;letter-spacing:.03em;text-transform:uppercase;margin-bottom:5px;color:var(--orange2)}
.callout.imp{border-left-color:#e5484d;background:#fdeeee}
.callout.imp .cl-t{color:#c73b40}
.callout.tip{border-left-color:#1e9e63;background:#eefaf2}
.callout.tip .cl-t{color:#178452}
.callout p{margin:0}
.callout p+p{margin-top:8px}
.article .faq{border-top:1px solid var(--line);padding:16px 0}
.article .faq h3{font-size:18px;margin:0 0 8px}
.article .faq p{font-size:16px;line-height:1.7;color:#26262b;margin:0}
/* ===== ФИНАЛЬНЫЙ CTA-БЛОК (низ статьи, самое важное) ===== */
.ctafinal{background:linear-gradient(150deg,#2b3140 0%,#1d2129 100%);border-radius:22px;padding:34px 34px 30px;margin:46px 0 24px;box-shadow:0 18px 44px rgba(20,22,28,.22)}
.cta-in{max-width:560px}
.ctafinal h2{margin:0 0 12px;font-size:26px;line-height:1.2;color:#fff}
.ctafinal p{font-size:16.5px;line-height:1.65;color:#c3c8d2;margin:0 0 20px}
.ctaform{margin:0 0 16px}
.ctarow{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.ctaform input[name=name],.ctaform input[name=phone]{width:100%;padding:15px 16px;border:1.5px solid #3a4150;border-radius:13px;font:inherit;font-size:16px;background:#fff;color:var(--navy)}
.ctaform input::placeholder{color:#9aa0ad}
.ctaform input:focus{outline:none;border-color:var(--orange);box-shadow:0 0 0 3px rgba(239,115,32,.2)}
.ctabtn{border:0;cursor:pointer;width:100%;font-size:17px;font-weight:800;padding:16px;border-radius:13px;background:var(--orange);color:#fff;transition:.15s}
.ctabtn:hover{background:var(--orange2)}
.ctaform .lf-ok{display:none;background:rgba(46,193,107,.15);border:1px solid rgba(46,193,107,.4);border-radius:13px;padding:14px 16px;margin-top:12px;font-weight:600;color:#7ce3a1}
.ctaform .lf-err{display:none;color:#ff9ea2;margin-top:12px;font-size:14px}
.tgbtn{display:inline-flex;align-items:center;gap:9px;background:#29a9eb;color:#fff;text-decoration:none;font-weight:700;font-size:15.5px;padding:12px 18px;border-radius:12px;margin:0 0 14px;transition:.15s}
.tgbtn:hover{background:#1f95d1}
.tgbtn svg{flex:0 0 auto}
.ctacall{font-size:17px;color:#c3c8d2;margin:4px 0 10px}
.ctacall a{color:#ffb057;font-weight:800;text-decoration:none;white-space:nowrap;border-bottom:1px solid rgba(255,176,87,.4)}
.ctapriv{font-size:12.5px;color:#7a808c;margin:0}
.ctapriv a{color:#9aa0ad}
@media(max-width:640px){.ctafinal{padding:26px 20px 24px;border-radius:18px}.ctafinal h2{font-size:22px}.ctarow{grid-template-columns:1fr}}
/* ===== ПРЕМИУМ ФУТЕР СТАТЬИ ===== */
.artfooter{margin:44px 0 30px;padding:28px 30px 22px;background:var(--soft);border:1px solid var(--line);border-radius:20px}
.af-top{display:flex;justify-content:space-between;gap:30px;flex-wrap:wrap;padding-bottom:20px;border-bottom:1px solid var(--line)}
.af-brand{max-width:340px}
.af-logo{font-weight:800;font-size:21px;color:var(--navy)}.af-logo b{color:var(--orange)}
.af-brand p{font-size:14px;line-height:1.55;color:var(--muted);margin:10px 0 0}
.af-contacts{display:flex;flex-direction:column;gap:11px}
.af-contacts a,.af-contacts .af-addr{display:flex;align-items:center;gap:9px;color:var(--navy);text-decoration:none;font-size:15px;font-weight:600}
.af-contacts svg{color:var(--orange);flex:0 0 auto}
.af-contacts .af-addr{color:var(--muted);font-weight:500;font-size:14px;max-width:320px}
.af-contacts a:hover{color:var(--orange)}
.af-bottom{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding:18px 0 0}
.af-links{display:flex;gap:20px;flex-wrap:wrap}
.af-links a{color:var(--navy);text-decoration:none;font-size:14.5px;font-weight:600}
.af-links a:hover{color:var(--orange)}
.af-up{display:inline-flex;align-items:center;gap:5px;color:var(--orange);text-decoration:none;font-weight:700;font-size:14px}
.af-copy{margin-top:16px;font-size:12.5px;color:var(--ink3,#9aa0b4)}
@media(max-width:640px){.artfooter{padding:22px 18px 18px}.af-top{flex-direction:column;gap:18px}.af-bottom{flex-direction:column;align-items:flex-start;gap:14px}}
@media(max-width:640px){.article h1{font-size:27px}.asec h2{font-size:22px}}
""".strip()



# Яндекс.Метрика для статических страниц (авто-hit) + цели-клики tel/mail/tg
METRIKA = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}
k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
(window,document,'script','https://mc.yandex.ru/metrika/tag.js?id=110603522','ym');
ym(110603522,'init',{ssr:true,webvisor:true,clickmap:true,ecommerce:"dataLayer",accurateTrackBounce:true,trackLinks:true});
window.ymGoal=function(n){try{ym(110603522,'reachGoal',n);}catch(_){}};
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href]');if(!a)return;
var h=a.getAttribute('href')||'';
if(h.indexOf('tel:')===0)window.ymGoal('phone_click');
else if(h.indexOf('mailto:')===0)window.ymGoal('email_click');
else if(h.indexOf('t.me')>-1||h.indexOf('wa.me')>-1)window.ymGoal('messenger');});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/110603522" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""


def lead_form_block(service_name):
    """Форма заявки на статической посадочной: POST в /send.php, цель form_submit."""
    svc = esc(service_name)
    return ("""<div class="contact" id="zayavka"><h2 style="margin-top:0">Получить разбор объекта</h2>
<p>Оставьте телефон: эксперт KEO GROUP разберёт вашу ситуацию и предложит порядок действий, сроки и стоимость. Перезвоним в течение 2 часов в рабочее время.</p>
<form id="lf" novalidate style="max-width:460px">
<input name="name" placeholder="Как к вам обращаться" autocomplete="name" style="display:block;width:100%;padding:12px 14px;margin:0 0 10px;border:1px solid #d9dde3;border-radius:10px;font:inherit;font-size:16px">
<input name="phone" placeholder="+7 999 123 45 67" inputmode="tel" autocomplete="tel" style="display:block;width:100%;padding:12px 14px;margin:0 0 10px;border:1px solid #d9dde3;border-radius:10px;font:inherit;font-size:16px">
<input type="hidden" name="service" value="""" + svc + """">
<input type="hidden" name="_subject" value="Заявка с посадочной KEO GROUP">
<div style="position:absolute;left:-9999px" aria-hidden="true"><input name="_gotcha" tabindex="-1" autocomplete="off"></div>
<button type="submit" class="btn" style="border:0;cursor:pointer;width:100%;font-size:15px">Отправить заявку</button>
<p style="font-size:12px;color:#6b7280;margin:8px 0 0">Отправляя форму, вы соглашаетесь с <a href="../../#/politika">политикой конфиденциальности</a>.</p>
<div id="lf-ok" style="display:none;background:#e9f7ef;border:1px solid #bfe6cd;border-radius:10px;padding:12px 14px;margin-top:10px;font-weight:600">Спасибо, заявка принята. Эксперт свяжется с вами в ближайшее время.</div>
<div id="lf-err" style="display:none;color:#b42318;margin-top:10px;font-size:13.5px">Не получилось отправить. Позвоните нам: """ + PHONE + """</div>
</form>
<script>
(function(){var f=document.getElementById('lf');if(!f)return;
f.addEventListener('submit',function(e){e.preventDefault();
var n=f.name.value.trim(),p=(f.phone.value||'').replace(/[^0-9]/g,'');
if(n.length<2){f.name.style.borderColor='#b42318';return;}else{f.name.style.borderColor='#d9dde3';}
if(p.length<11){f.phone.style.borderColor='#b42318';return;}else{f.phone.style.borderColor='#d9dde3';}
if(f._gotcha&&f._gotcha.value)return;
var b=f.querySelector('button');b.disabled=true;b.textContent='Отправляем…';
fetch('/send.php',{method:'POST',headers:{Accept:'application/json'},body:new FormData(f)})
.then(function(r){if(r.ok){window.ymGoal&&window.ymGoal('form_submit');
document.getElementById('lf-ok').style.display='block';f.reset();b.textContent='Отправить заявку';b.disabled=false;}
else{throw 0;}})
.catch(function(){document.getElementById('lf-err').style.display='block';b.disabled=false;b.textContent='Отправить заявку';});});})();
</script></div>"""
    )



def head_html(title, desc, canonical, jsonld_blocks, og_image=None):
    ld = "\n".join(
        f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>'
        for b in jsonld_blocks)
    og_img = og_image or (BASE_URL + "images/brand/keo-logo.jpg")
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<link rel="icon" href="{BASE_URL}favicon.ico" sizes="any">
<link rel="icon" type="image/svg+xml" href="{BASE_URL}favicon.svg">
<link rel="apple-touch-icon" href="{BASE_URL}apple-touch-icon.png">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="KEO GROUP">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{og_img}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
{ld}
{METRIKA}
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


def nav_menu():
    """Верхнее меню-навигация (на всех статических страницах)."""
    return (
        '<nav class="mainnav"><div class="wrap navwrap">'
        '<a class="logo" href="../../">KEO <span>GROUP</span></a>'
        '<div class="navlinks">'
        '<a href="../../">Главная</a>'
        '<a href="../../#/uslugi">Услуги</a>'
        '<a href="../krt-zashchita/">КРТ</a>'
        '<a href="../rosreestr-priostanovki/">Росреестр</a>'
        '<a href="/spravochnik/">Справочник</a>'
        '<a href="../../#/o-kompanii">О компании</a>'
        '</div>'
        f'<a class="navphone" href="tel:{PHONE_TEL}">{PHONE}</a>'
        '</div></nav>'
    )


def soft_help_block(name, group_title, cta=None):
    """Финальный CTA-блок статьи. Заголовок и текст — СВОИ под тему страницы (cta),
    иначе общий запасной. Тёмный премиум, форма (имя+телефон), крупный телефон."""
    svc = esc(f"Справочник: {name}")
    cta = cta or {}
    h = esc(cta.get("h") or "Поможем с вашим участком или объектом")
    ptext = esc(cta.get("p") or "Расскажите про свою ситуацию: эксперт KEO GROUP разберёт её и подскажет порядок действий, сроки и стоимость. За плечами команды более 25 лет практики. Перезвоним в течение 2 часов в рабочее время.")
    return ("""<aside class="ctafinal" id="zayavka"><div class="cta-in">
<h2>""" + h + """</h2>
<p>""" + ptext + """</p>
<form id="lf" novalidate class="ctaform">
<div class="ctarow">
<input name="name" placeholder="Как к вам обращаться" autocomplete="name">
<input name="phone" placeholder="Ваш телефон" inputmode="tel" autocomplete="tel">
</div>
<input type="hidden" name="service" value=\"""" + svc + """">
<input type="hidden" name="_subject" value="Заявка со статьи KEO GROUP">
<div style="position:absolute;left:-9999px" aria-hidden="true"><input name="_gotcha" tabindex="-1" autocomplete="off"></div>
<button type="submit" class="btn ctabtn">Отправить заявку</button>
<div id="lf-ok" class="lf-ok">Спасибо, заявка принята. Эксперт свяжется с вами в ближайшее время.</div>
<div id="lf-err" class="lf-err">Не получилось отправить, позвоните нам: """ + PHONE + """</div>
</form>
<a class="tgbtn" href="https://t.me/""" + TELEGRAM + """" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor" d="M21.9 4.3l-3.3 15.6c-.2 1.1-.9 1.4-1.8.9l-5-3.7-2.4 2.3c-.3.3-.5.5-1 .5l.4-5.1 9.3-8.4c.4-.4-.1-.6-.6-.2L4.7 13.4l-4.9-1.5c-1.1-.3-1.1-1 .2-1.6L20.5 2.6c.9-.3 1.7.2 1.4 1.7z"/></svg><span>Написать в Telegram и прислать документы</span></a>
<div class="ctacall">Или позвоните прямо сейчас: <a href="tel:""" + PHONE_TEL + '">' + PHONE + """</a></div>
<div class="ctapriv">Отправляя форму, вы соглашаетесь с <a href="../../#/politika">политикой конфиденциальности</a>.</div>
</div>
<script>
(function(){var f=document.getElementById('lf');if(!f)return;
f.addEventListener('submit',function(e){e.preventDefault();
var n=f.name.value.trim(),p=(f.phone.value||'').replace(/[^0-9]/g,'');
if(n.length<2){f.name.style.borderColor='#e5484d';return;}else{f.name.style.borderColor='';}
if(p.length<11){f.phone.style.borderColor='#e5484d';return;}else{f.phone.style.borderColor='';}
if(f._gotcha&&f._gotcha.value)return;
var b=f.querySelector('button');b.disabled=true;b.textContent='Отправляем…';
fetch('/send.php',{method:'POST',headers:{Accept:'application/json'},body:new FormData(f)})
.then(function(r){if(r.ok){window.ymGoal&&window.ymGoal('form_submit');
document.getElementById('lf-ok').style.display='block';f.reset();b.textContent='Отправить заявку';b.disabled=false;}else{throw 0;}})
.catch(function(){document.getElementById('lf-err').style.display='block';b.disabled=false;b.textContent='Отправить заявку';});});})();
</script>
</aside>""")


def art_footer():
    """Премиальный футер статьи в размер контента: логотип, контакты с иконками, ссылки, наверх."""
    ic_pin = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 2C8.1 2 5 5.1 5 9c0 5.2 7 13 7 13s7-7.8 7-13c0-3.9-3.1-7-7-7zm0 9.5A2.5 2.5 0 1112 6.5a2.5 2.5 0 010 5z"/></svg>'
    ic_tel = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M6.6 10.8c1.4 2.8 3.8 5.2 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.4.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1l-2.3 2.2z"/></svg>'
    ic_mail = '<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zm8 7l8-4.5V6l-8 4.5L4 6v.5L12 11z"/></svg>'
    ic_up = '<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M12 5l7 7-1.4 1.4L13 8.8V19h-2V8.8l-4.6 4.6L5 12z"/></svg>'
    return (
        '<footer class="artfooter">'
        '<div class="af-top">'
        '<div class="af-brand"><span class="af-logo">KEO <b>GROUP</b></span>'
        '<p>Юридическое и градостроительное сопровождение коммерческой недвижимости в Москве.</p></div>'
        '<div class="af-contacts">'
        f'<a href="tel:{PHONE_TEL}">{ic_tel}<span>{PHONE}</span></a>'
        f'<a href="mailto:{EMAIL}">{ic_mail}<span>{EMAIL}</span></a>'
        f'<span class="af-addr">{ic_pin}<span>{esc(ADDRESS)}, {esc(METRO)}</span></span>'
        '</div></div>'
        '<div class="af-bottom">'
        '<div class="af-links"><a href="../../">На главную</a><a href="../../#/uslugi">Услуги</a>'
        '<a href="../../#/o-kompanii">О компании</a><a href="../../#/kontakty">Контакты</a></div>'
        f'<a href="#top" class="af-up">{ic_up}Наверх</a>'
        '</div>'
        '<div class="af-copy">© 2026 KEO GROUP. Все права защищены.</div>'
        '</footer>'
    )


def article_page_html(slug, rich_d, services, groups, prices, name, title, desc, url, group_title, g_key):
    """Шаблон ИНФО-СТАТЬИ (лонгрид): меню сверху → H1 → интро → оглавление →
    большой текст разделами → FAQ → и только в конце мягкий блок помощи."""
    h1 = rich_d.get("h1") or name
    intro = rich_d.get("intro") or rich_d.get("lede") or ""
    toc = rich_d.get("toc") or []
    sections = rich_d.get("sections") or []
    faq = rich_d.get("faq") or []
    stats = rich_d.get("stats") or []
    hero_img = rich_d.get("img") or slug
    body = []
    # HERO с картинкой на первом экране
    body.append(
        f'<div class="ahero" style="background-image:linear-gradient(180deg,rgba(20,22,28,.28),rgba(20,22,28,.82)),url(../../images/land/{esc(hero_img)}.jpg)">'
        f'<div class="ahero-in">'
        f'<p class="crumbs light"><a href="../../">Главная</a> / <a href="/spravochnik/">Справочник</a> / {esc(group_title)}</p>'
        f'<div class="eyebrow light">{esc(group_title)}</div>'
        f'<h1>{esc(h1)}</h1>'
        f'</div></div>'
    )
    if intro:
        body.append(f'<p class="lede">{esc(intro)}</p>')
    # КАРТОЧКИ КЛЮЧЕВЫХ ФАКТОВ (инфографика)
    if stats:
        body.append('<div class="statcards">')
        for pair in stats[:4]:
            body.append(f'<div class="statcard"><b>{esc(pair[0])}</b><span>{esc(pair[1])}</span></div>')
        body.append('</div>')
    if rich_d.get("updated"):
        body.append(f'<p class="upd">Обновлено: {esc(rich_d["updated"])}</p>')
    if toc:
        body.append('<nav class="toc"><div class="toc-t">Содержание</div><ol>')
        for item in toc:
            tid, ttitle = item[0], item[1]
            body.append(f'<li><a href="#{esc(tid)}">{esc(ttitle)}</a></li>')
        body.append('</ol></nav>')
    for sec in sections:
        sid = esc(sec.get("id", ""))
        sh2 = esc(sec.get("h2", ""))
        shtml = sec.get("html", "")  # доверенный HTML от копирайтера
        body.append(f'<section class="asec"><h2 id="{sid}">{sh2}</h2>{shtml}</section>')
    if faq:
        body.append('<h2 id="faq">Частые вопросы</h2>')
        for q, a in faq:
            body.append(f'<div class="faq"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>')
    body.append(soft_help_block(h1, group_title, rich_d.get("cta")))
    # смежные материалы той же группы
    rel = [s for s in services if s["g"] == g_key and s["slug"] != slug][:4]
    if rel:
        body.append('<h2>Смежные материалы</h2><ul class="plain rel">')
        for r in rel:
            body.append(f'<li><a href="../{r["slug"]}/">{esc(r["name"])}</a> <span class="muted">{esc(r["note"])}</span></li>')
        body.append("</ul>")
    jsonld = jsonld_for(slug, name, desc, faq, "", group_title)
    # og-картинка = тематическая картинка статьи (НЕ логотип), берём hero-изображение
    land_img = SITE_DIR / "images" / "land" / f"{hero_img}.jpg"
    og_image = f"{BASE_URL}images/land/{hero_img}.jpg" if land_img.exists() else None
    return f"""{head_html(title, desc, url, jsonld, og_image=og_image)}
<body>
{nav_menu()}
<main id="top"><div class="wrap article">
{chr(10).join(body)}
{art_footer()}
</div></main>
</body>
</html>
"""


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
    # инфо-страница (статья-лонгрид) рендерится отдельным шаблоном
    if (rich_d or {}).get("sections"):
        return article_page_html(slug, rich_d, services, groups, prices, name, title, desc, url, group_title, g_key)
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
    body.append('<a class="btn" href="#zayavka" style="margin-left:8px;background:#fff;color:#bd560b;border:2px solid #ef7320">Оставить заявку</a>')

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

    # форма заявки (посадочная для рекламы)
    body.append(lead_form_block(name))

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
    land_img = SITE_DIR / "images" / "land" / f"{slug}.jpg"
    og_image = f"{BASE_URL}images/land/{slug}.jpg" if land_img.exists() else None
    return f"""{head_html(title, desc, url, jsonld, og_image=og_image)}
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
