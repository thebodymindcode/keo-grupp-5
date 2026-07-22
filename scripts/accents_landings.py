#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Врезки-акценты (callout) на рекламные лендинги. Идемпотентно: повторный запуск не дублирует.
Вставка отдельной мини-секцией ПЕРЕД блоком «Как работаем». Факты взяты с самих страниц.
Применяет к u/<slug>/ и _mpsite/u/<slug>/. Запускать после любых пересборок страниц."""
import pathlib

SITE = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = '>Как работаем</div>'
MARK = 'data-accent="landing"'

CALLOUTS = {
 'krt-zashchita': ('imp', 'Действуйте на опережение',
   'За 5,5 месяца 2026 года в Москве и области выпущено <mark>220+ решений об изъятии</mark>. '
   'Средний прирост компенсации в наших делах <mark>+109%</mark>, и каждое дело проверяется в картотеке арбитража по номеру.'),
 'rosreestr-priostanovki': ('imp', 'Почему это срочно',
   '<mark>70% заявок</mark> получают приостановку из-за ошибок в документах. Пока она не снята, объект '
   'нельзя продать, сдать в аренду или заложить, а повторные работы добавляют <mark>50-100% к стоимости</mark>.'),
 'dgi-vykup-159fz': ('tip', 'На заметку',
   'Городская оценка при выкупе нередко завышена <mark>на 30-80% выше рынка</mark>. '
   'По нашим делам выкупную цену удавалось снижать <mark>на 30-50%</mark>.'),
 'vri-zemelnogo-uchastka': ('imp', 'Сколько стоит нарушение',
   'Штраф от ГИН за использование участка не по ВРИ: <mark>1,5-2% кадастровой стоимости, минимум 100 000 ₽</mark>. '
   'Пока ВРИ не приведён в порядок, аренда не регистрируется и строить нельзя.'),
 'legalizaciya-819pp': ('tip', 'Гарантия в договоре',
   'Исключение из 819-ПП: от 250 000 ₽, срок от 5 до 15 месяцев. В договоре гарантия: <mark>результат или возврат</mark>. '
   'За плечами 30+ проектов на 30 000+ кв.м узаконенных площадей.'),
 'nekapitalnye-obekty': ('', 'На заметку',
   'Согласование под ключ от 180 000 ₽, только проект от 100 000 ₽ (документация, чертежи, 3D-визуализация). '
   'За плечами <mark>80+ согласованных некапитальных объектов</mark>.'),
}

def block(kind, title, text):
    cls = ('callout ' + kind).strip()
    return (f'<section style="padding-top:0" {MARK}><div class="wrap">'
            f'<div class="{cls}" style="max-width:860px;font-size:16px">'
            f'<span class="cl-t">{title}</span><p>{text}</p></div></div></section>')

changed = 0
for slug, (kind, title, text) in CALLOUTS.items():
    for base in (SITE / 'u', SITE / '_mpsite' / 'u'):
        f = base / slug / 'index.html'
        if not f.exists():
            continue
        h = f.read_text(encoding='utf-8')
        if MARK in h:            # уже вставлено
            continue
        i = h.find(ANCHOR)
        if i < 0:
            print('  ⚠ нет якоря:', f)
            continue
        # начало секции, содержащей якорь
        j = h.rfind('<section', 0, i)
        if j < 0:
            print('  ⚠ нет <section до якоря:', f)
            continue
        h = h[:j] + block(kind, title, text) + h[j:]
        f.write_text(h, encoding='utf-8')
        changed += 1
        print('  ✓', f.relative_to(SITE))
print('вставлено врезок:', changed)
