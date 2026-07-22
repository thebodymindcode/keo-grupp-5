#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Деплой статического сайта keo-grupp-5 на хостинг Beget по FTP (папка главного сайта keogroup.ru).
Заливает только новые и изменившиеся по размеру файлы (текстовые index/404/robots/sitemap/.htaccess
льёт всегда). НЕ трогает почту, DNS и поддомены (аккаунт FTP закрыт на /keogroup.ru/public_html).
Креды берёт из ../.beget_ftp (в git не хранится).
Запуск:  python3 scripts/deploy_beget.py
"""
import ftplib, os, sys
HERE=os.path.dirname(os.path.abspath(__file__)); SITE=os.path.dirname(HERE)
cfg={}
for line in open(os.path.join(SITE,".beget_ftp"),encoding="utf-8"):
    line=line.strip()
    if "=" in line and not line.startswith("#"):
        k,v=line.split("=",1); cfg[k.strip()]=v.strip()
HOST,USER,PW=cfg["host"],cfg["user"],cfg["pass"]

WHITELIST_DIRS=["files","u","images"]
FAVICONS=["favicon.ico","favicon.svg","favicon-32.png","apple-touch-icon.png","icon-192.png","icon-512.png"]
WHITELIST_ROOT=["404.html","robots.txt","sitemap.xml","send.php","index.html",".htaccess"]+FAVICONS
ALWAYS=set(["index.html","404.html","robots.txt","sitemap.xml","send.php",".htaccess"]+FAVICONS)  # текст/скрипт/иконки всегда

ftp=ftplib.FTP(); ftp.connect(HOST,21,timeout=120); ftp.login(USER,PW); ftp.set_pasv(True)
made=set()
def ensure(remote):
    cur=""
    for p in remote.strip("/").split("/"):
        cur+="/"+p
        if cur in made: continue
        try: ftp.mkd(cur)
        except: pass
        made.add(cur)
def rsize(remote):
    try: return ftp.size(remote)
    except: return -1
def put(lp,rp):
    with open(lp,"rb") as fh: ftp.storbinary("STOR "+rp, fh, blocksize=1024*256)

up=0; skip=0
def sync_file(lp, rp, always=False):
    global up,skip
    name=os.path.basename(rp)
    if always or name in ALWAYS or rsize(rp)!=os.path.getsize(lp):
        ensure(os.path.dirname(rp)); put(lp,rp); up+=1
    else: skip+=1

for d in WHITELIST_DIRS:
    base=os.path.join(SITE,d)
    if not os.path.isdir(base): continue
    for root,dirs,files in os.walk(base):
        rel=os.path.relpath(root,SITE).replace(os.sep,"/")
        for fn in files:
            sync_file(os.path.join(root,fn), "/"+rel+"/"+fn)
# корневые файлы в конце (index и .htaccess последними = атомарное переключение)
for f in ["404.html","robots.txt","sitemap.xml","send.php","index.html",".htaccess"]:
    p=os.path.join(SITE,f)
    if os.path.exists(p): sync_file(p,"/"+f, always=True)

print(f"Деплой на Beget готов: залито {up}, пропущено (без изменений) {skip}")
print("Сайт: https://keogroup.ru/")
ftp.quit()
