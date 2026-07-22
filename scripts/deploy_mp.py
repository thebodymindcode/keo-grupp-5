#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import ftplib, os, time, pathlib
SITE=pathlib.Path.home()/'.business/sites/out/keo-grupp-5'
MP=SITE/'_mpsite'
cfg={}
for line in open(SITE/'.beget_ftp',encoding='utf-8'):
    line=line.strip()
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1); cfg[k.strip()]=v.strip()
HOST,USER,PW=cfg['host'],cfg['user'],cfg['pass']

# собрать список (local_path, remote_path)
SKIP_DIRS={'images','files','assets'}  # симлинки/уже на сервере (assets грузим отдельно real)
SKIP_FILES={'send.php','favicon.ico','favicon.svg','favicon-32.png','apple-touch-icon.png','icon-192.png','icon-512.png'}
pages=[]
for root,dirs,files in os.walk(MP, followlinks=False):
    dirs[:]=[d for d in dirs if d not in SKIP_DIRS and not os.path.islink(os.path.join(root,d))]
    for fn in files:
        lp=os.path.join(root,fn)
        if os.path.islink(lp): continue
        if fn in SKIP_FILES: continue
        rel=os.path.relpath(lp,MP).replace(os.sep,'/')
        pages.append((lp,'/'+rel))
# assets (реальные файлы)
assets=[(str(SITE/'assets/site.css'),'/assets/site.css'),(str(SITE/'assets/app.js'),'/assets/app.js')]

# порядок: assets -> страницы(кроме index.html/.htaccess) -> index.html -> .htaccess
def is_last(rp): return rp in ('/index.html','/.htaccess')
first=assets+[(lp,rp) for lp,rp in pages if not is_last(rp)]
idx=[(lp,rp) for lp,rp in pages if rp=='/index.html']
hta=[(lp,rp) for lp,rp in pages if rp=='/.htaccess']
ordered=first+idx+hta
print("файлов к заливке:",len(ordered))

def connect():
    ftp=ftplib.FTP(); ftp.connect(HOST,21,timeout=300); ftp.login(USER,PW); ftp.set_pasv(True); return ftp
made=set()
def ensure(ftp,remote):
    cur=''
    for p in remote.strip('/').split('/')[:-1]:
        cur+='/'+p
        if cur in made: continue
        try: ftp.mkd(cur)
        except: pass
        made.add(cur)
ftp=connect(); up=0; fails=[]
for i,(lp,rp) in enumerate(ordered,1):
    ok=False
    for att in range(1,5):
        try:
            ensure(ftp,rp)
            with open(lp,'rb') as fh: ftp.storbinary('STOR '+rp, fh, blocksize=1024*512)
            ok=True; up+=1; break
        except Exception as e:
            try: ftp.quit()
            except: pass
            time.sleep(2)
            try: ftp=connect()
            except: time.sleep(3); ftp=connect()
    if not ok: fails.append(rp)
    if i%15==0: print(f"  {i}/{len(ordered)} залито...")
try: ftp.quit()
except: pass
print(f"ГОТОВО: залито {up}/{len(ordered)}")
if fails: print("НЕ ЗАЛИЛИСЬ:",fails)
else: print("все файлы на месте. Сайт: https://keogroup.ru/")
