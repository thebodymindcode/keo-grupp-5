#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Держит число статей в лиде справочника В СООТВЕТСТВИИ с реальным количеством карточек.
Раньше было зашито «5 статей», статьи добавлялись, а число врало. Теперь считаем kbitem и правим,
с правильным русским склонением. Запускать шагом маршрута выпуска после добавления карточки.
"""
import pathlib, re, sys

SPR = pathlib.Path.home()/".business/sites/out/keo-grupp-5/_mpsite/spravochnik/index.html"

def plural(n):
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11: return "статья"
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14: return "статьи"
    return "статей"

def main():
    s = SPR.read_text(encoding="utf-8")
    count = s.count('class="kbitem"')
    if count == 0:
        print("kbitem не найдены, пропуск"); return 1
    new = f"{count}&nbsp;{plural(count)}"
    # заменяем «<число>&nbsp;стат...» в лиде
    s2 = re.sub(r"\d+&nbsp;стат[а-я]+", new, s, count=1)
    if s2 == s:
        print(f"число уже актуально или шаблон не найден (карточек {count})"); return 0
    SPR.write_text(s2, encoding="utf-8")
    print(f"справочник: {new.replace('&nbsp;', ' ')} (карточек {count})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
