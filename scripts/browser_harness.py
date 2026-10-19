#!/usr/bin/env python3
"""Local UI verification harness. Production builds never include this server.

Uses the real source worker, with synthetic files in place of native dialogs.
This checks the renderer independently when a host cannot start Electron.
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import mimetypes
import uuid
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "test-artifacts" / "browser"
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "input.csv").write_text("Label,Value\nA,1\nB,2\nC,3\n")
(OUTPUT / "input.spjs").write_text(json.dumps({"workbook":{"sheets":{"Data":{"index":0,"data":{"dataTable":{"0":{"0":{"value":"Original cell"},"1":{"value":42}},"1":{"0":{"value":"Cached formula"},"1":{"value":84,"formula":"B1*2"}}}}}}},"charts":[]}))
worker = subprocess.Popen([sys.executable, "-u", "-m", "backend.worker"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
lock = threading.Lock()
import_index = 0
favorites = []

def engine(method, params=None):
    with lock:
        worker.stdin.write(json.dumps({"id":"browser", "method":method, "params":params or {}})+"\n")
        worker.stdin.flush()
        result=json.loads(worker.stdout.readline())
    if not result["ok"]: raise ValueError(result["error"])
    return result["result"]

BRIDGE = r"""
async function request(method,params){const response=await fetch('/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({method,params})});const message=await response.json();if(!message.ok)throw new Error(message.error);return message.result;}
window.workbench={catalog:()=>request('catalog'),analyze:p=>request('analyze',p),importData:p=>request('import',p),exportData:p=>request('export',p),saveProject:p=>request('save',p),openProject:()=>request('open'),saveReport:p=>request('report',p),listFavorites:()=>request('favorites'),saveFavorite:p=>request('favorite-save',p),deleteFavorite:id=>request('favorite-delete',id),setDirty:()=>{},onMenu:()=>()=>{}};
window.addEventListener('DOMContentLoaded',()=>{if(!new URLSearchParams(location.search).has('verify'))return;const button=document.createElement('button');button.id='verify-ui';button.textContent='Run integration check';button.style.cssText='position:fixed;bottom:5px;right:10px;z-index:100;font-size:11px';button.onclick=async()=>{button.disabled=true;try{await request('begin');const result=await window.runDesktopSmokeTest();await request('result',result);button.textContent='Integration checks passed';button.style.background='#d8f5e6';}catch(error){button.textContent='Check failed: '+error.message;button.style.background='#ffd7d7';await request('result',{ok:false,error:error.message});}finally{button.disabled=false;}};document.body.append(button);});
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def response(self,content,mime="application/json",code=200):
        raw=content.encode() if isinstance(content,str) else content
        self.send_response(code);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=="/bridge.js": return self.response(BRIDGE,"text/javascript")
        relative=unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
        static=ROOT/'renderer-dist'
        file=(static/relative).resolve()
        if not file.is_relative_to(static.resolve()) or not file.is_file(): return self.response("Not found","text/plain",404)
        content=file.read_bytes()
        if relative=="index.html": content=content.decode().replace("connect-src 'none'","connect-src 'self'").replace('</head>','<script src="/bridge.js"></script></head>')
        self.response(content,mimetypes.guess_type(file)[0] or "application/octet-stream")
    def do_POST(self):
        global import_index, favorites
        if self.path!="/api" or self.headers.get("Origin")!=f"http://127.0.0.1:{self.server.server_port}": return self.response("Forbidden","text/plain",403)
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=32*1024*1024: raise ValueError("Invalid request size")
            body=json.loads(self.rfile.read(length));method=body["method"];p=body.get("params")
            if method=="begin": import_index=0;result=True
            elif method=="favorites": result=favorites
            elif method=="favorite-save":
                result={**p,"favoriteId":str(uuid.uuid4())};favorites.append(result)
            elif method=="favorite-delete":
                favorites=[f for f in favorites if f["favoriteId"]!=p];result=True
            elif method in {"catalog","analyze"}: result=engine(method,p)
            elif method=="import":
                file=OUTPUT/("input.csv" if import_index==0 else "input.spjs");import_index+=1
                result=engine("import_file",{"path":str(file)});result['importPath']=str(file)
            elif method=="export":
                file=OUTPUT/"export.csv";engine("export_file",{"path":str(file),"data":p});result=str(file)
            elif method=="save":
                file=OUTPUT/"smoke.statworkbench.json";file.write_text(json.dumps(p));result=str(file)
            elif method=="open": result=json.loads((OUTPUT/"smoke.statworkbench.json").read_text())
            elif method=="report":
                file=OUTPUT/"report.html";file.write_text(p);result=str(file)
            elif method=="result":
                (OUTPUT/"browser-smoke.json").write_text(json.dumps(p,indent=2));result=True
            else: raise ValueError("Unknown test operation")
            self.response(json.dumps({"ok":True,"result":result}))
        except Exception as exc: self.response(json.dumps({"ok":False,"error":str(exc)}))

server=ThreadingHTTPServer(('127.0.0.1',8767),Handler)
print('Browser verification: http://127.0.0.1:8767',flush=True)
try: server.serve_forever()
finally: worker.terminate();server.server_close()
