#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Инфографика этапов на рекламных лендингах: кружок-номер + SVG-иконка по теме шага +
стрелки процесса (CSS .steps в assets/site.css). Идемпотентно (маркер data-infog).
Применяет к u/<slug>/ и _mpsite/u/<slug>/. Запускать после пересборок страниц."""
import re, pathlib

SITE = pathlib.Path(__file__).resolve().parent.parent

SLUGS = ['krt-zashchita','rosreestr-priostanovki','izmeneniya-egrn','registraciya-dogovorov',
         'razdel-obedinenie','registraciya-prava','dgi-vykup-159fz','dgi-lgotnaya-arenda',
         'vri-zemelnogo-uchastka','pmt-pzz','legalizaciya-819pp','nekapitalnye-obekty',
         'zashchita-ot-snosa-sud']

SW = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
ICONS = {
 'lupa':   f'<svg viewBox="0 0 24 24" {SW}><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/><path d="M8 10.5h5M10.5 8v5"/></svg>',
 'doc':    f'<svg viewBox="0 0 24 24" {SW}><path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></svg>',
 'send':   f'<svg viewBox="0 0 24 24" {SW}><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/><path d="M12 15V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/></svg>',
 'shield': f'<svg viewBox="0 0 24 24" {SW}><path d="M12 3l7 3v5.5c0 4.3-3 7.4-7 8.5-4-1.1-7-4.2-7-8.5V6l7-3z"/><path d="m9.2 12 2 2 3.6-3.8"/></svg>',
 'scales': f'<svg viewBox="0 0 24 24" {SW}><path d="M12 3v18M5 7h14"/><path d="M7 7l-3 6a3.5 3.5 0 0 0 6 0z"/><path d="M17 7l-3 6a3.5 3.5 0 0 0 6 0z"/><path d="M8 21h8"/></svg>',
 'build':  f'<svg viewBox="0 0 24 24" {SW}><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 21v-5h6v5"/><path d="M9 10h.01M15 10h.01"/></svg>',
 'coin':   f'<svg viewBox="0 0 24 24" {SW}><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v9M9.5 9.8c0-1.2 1.1-2 2.5-2s2.5.8 2.5 2-1.1 1.7-2.5 2-2.5.8-2.5 2 1.1 2 2.5 2 2.5-.8 2.5-2"/></svg>',
 'stamp':  f'<svg viewBox="0 0 24 24" {SW}><path d="M12 3a3 3 0 0 0-3 3c0 1.6.9 2.6 1.5 3.6.4.8-.1 1.4-1 1.4H7a2 2 0 0 0-2 2v2h14v-2a2 2 0 0 0-2-2h-2.5c-.9 0-1.4-.6-1-1.4.6-1 1.5-2 1.5-3.6a3 3 0 0 0-3-3z"/><path d="M5 19h14v2H5z"/></svg>',
 'map':    f'<svg viewBox="0 0 24 24" {SW}><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4z"/><path d="M9 4v14M15 6v14"/></svg>',
}
def pick_icon(title):
    t = title.lower()
    for keys, name in [
        (('аудит','анализ','разбор','провер','оцен','стратег'), 'lupa'),
        (('гзк','комисси','апелляц'), 'stamp'),
        (('суд','экспертиз','защит'), 'scales'),
        (('межеван','границ','схем','план территори','пмт','карта'), 'map'),
        (('документ','техплан','проект','пакет','заключен','подготов'), 'doc'),
        (('подач','подаём','сопровожден','ведём','росреестр','заявлен'), 'send'),
        (('стро','монтаж','надзор','ввод'), 'build'),
        (('цена','оплат','стоимост','выкуп','компенсац','сниж'), 'coin'),
        (('право','егрн','итог','результат','снятие','исключен','регистрац','запись'), 'shield'),
    ]:
        if any(k in t for k in keys):
            return ICONS[name]
    return ICONS['doc']

# карточка этапа: <div class="card"><div style="...color:#HEX...">NN</div><h3 ...>Título</h3>...
CARD_RE = re.compile(
    r'<div class="card">\s*<div style="font-size:38px;font-weight:800;color:(#[0-9a-fA-F]{3,6});line-height:1;margin-bottom:12px">(\d\d)</div>\s*<h3([^>]*)>(.*?)</h3>',
    re.S)

def upgrade(html):
    n = 0
    def repl(m):
        nonlocal n
        color, num, h3attrs, title = m.group(1), m.group(2), m.group(3), m.group(4)
        plain = re.sub(r'<[^>]+>', '', title)
        ic = pick_icon(plain)
        n += 1
        return (f'<div class="card"><div class="step-head" style="color:{color}">'
                f'<span class="step-num">{num}</span><span class="step-ic">{ic}</span></div>'
                f'<h3{h3attrs}>{title}</h3>')
    html = CARD_RE.sub(repl, html)
    return html, n

changed = 0
for slug in SLUGS:
    for base in (SITE / 'u', SITE / '_mpsite' / 'u'):
        f = base / slug / 'index.html'
        if not f.exists():
            continue
        h = f.read_text(encoding='utf-8')
        if 'step-num' in h:
            continue  # уже обработан
        # только внутри секции «Как работаем» (этапы) — ограничим область
        i = h.find('>Как работаем</div>')
        if i < 0:
            print('  ⚠ нет блока этапов:', slug)
            continue
        j = h.find('</section>', i)
        seg, n = upgrade(h[i:j])
        if n == 0:
            print('  ⚠ карточки этапов не распознаны:', slug)
            continue
        h = h[:i] + seg + h[j:]
        # пометить grid как .steps
        k = h.find('class="grid g4"', i)
        if 0 <= k < h.find('</section>', i):
            h = h[:k] + 'class="grid g4 steps" data-infog="1"' + h[k+len('class="grid g4"'):]
        f.write_text(h, encoding='utf-8')
        changed += 1
        print(f'  ✓ {f.relative_to(SITE)} (шагов: {n})')
print('обработано файлов:', changed)
