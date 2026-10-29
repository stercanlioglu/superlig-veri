# Uygulamayı AES-256-GCM ile şifreleyip giriş ekranlı index.html üretir (ve tersini yapar).
# Şifrele: python sifrele.py KULLANICI SIFRE [girdi=uygulama_acik.html] [cikti=index.html]
# Çöz:     python sifrele.py --coz KULLANICI SIFRE [girdi=index.html] [cikti=uygulama_acik.html]
import os, re, base64, hashlib, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
IT = 200000

def anahtar(user, pw, salt, it=IT):
    return hashlib.pbkdf2_hmac('sha256', (user.strip().lower() + ':' + pw).encode(), salt, it, 32)

PAGE = '''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Süper Lig Motoru</title>
<style>body{margin:0;font-family:-apple-system,system-ui,sans-serif;background:#f6f7f4;color:#161a16;display:flex;min-height:100vh;align-items:center;justify-content:center}
.box{background:#fff;border:1px solid #d9ddd3;border-radius:10px;padding:24px;width:min(360px,90vw)}h1{font-size:20px;margin:0 0 4px}p{color:#5a6158;font-size:13px;margin:0 0 16px}
label{display:block;font-size:13px;margin:10px 0 4px}input{width:100%;box-sizing:border-box;font:inherit;padding:10px;border:1px solid #d9ddd3;border-radius:6px}
button{margin-top:14px;width:100%;font:inherit;padding:11px;border:0;border-radius:6px;background:#1f6f4a;color:#fff;font-weight:600}
.err{color:#b3261e;font-size:13px;margin-top:10px;display:none}.rem{display:flex;gap:8px;align-items:center;font-size:13px;margin-top:10px}.rem input{width:auto}</style></head>
<body><form class="box" id="f"><h1>Süper Lig Motoru</h1><p>Bu sayfa şifrelidir. Kullanıcı adı ve şifrenizi girin.</p>
<label>Kullanıcı adı<input id="u" autocomplete="username" autocapitalize="none"></label>
<label>Şifre<input id="p" type="password" autocomplete="current-password"></label>
<div class="rem"><input type="checkbox" id="r" checked><label for="r" style="margin:0">Bu cihazda hatırla</label></div>
<button type="submit">Giriş</button><div class="err" id="e">Kullanıcı adı veya şifre hatalı.</div></form>
<script>
var S='__SALT__',IV='__IV__',CT='__CT__',IT=__IT__;
function b(s){return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0)})}
async function key(pass){var k=await crypto.subtle.importKey('raw',new TextEncoder().encode(pass),'PBKDF2',false,['deriveKey']);
 return crypto.subtle.deriveKey({name:'PBKDF2',salt:b(S),iterations:IT,hash:'SHA-256'},k,{name:'AES-GCM',length:256},true,['decrypt'])}
async function dec(k){var pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b(IV)},k,b(CT));return new TextDecoder().decode(pt)}
function ready(){return new Promise(function(r){if(document.readyState==='complete')r();else window.addEventListener('load',function(){r()})})}
async function show(h){await ready();var f=document.getElementById('f');if(f)f.remove();document.open();document.write(h);document.close()}
(async function(){try{var j=localStorage.getItem('slm_key');if(j){var k=await crypto.subtle.importKey('jwk',JSON.parse(j),{name:'AES-GCM'},true,['decrypt']);show(await dec(k))}}catch(e){}})();
async function tryPass(pass){try{var k=await key(pass);var h=await dec(k);return [k,h]}catch(e){return null}}
document.getElementById('f').addEventListener('submit',async function(ev){ev.preventDefault();var u=document.getElementById('u').value.trim().toLowerCase(),p=document.getElementById('p').value,rem=document.getElementById('r').checked;
 var r=await tryPass(u+':'+p); if(!r&&p.endsWith('.')) r=await tryPass(u+':'+p.slice(0,-1));
 if(!r){document.getElementById('e').style.display='block';return}
 if(rem){try{localStorage.setItem('slm_key',JSON.stringify(await crypto.subtle.exportKey('jwk',r[0])))}catch(e){}}
 show(r[1])});
</script></body></html>'''

def sifrele(html, user, pw):
    """Düz HTML (str) -> giriş ekranlı şifreli sayfa (str)."""
    salt = os.urandom(16); iv = os.urandom(12)
    ct = AESGCM(anahtar(user, pw, salt)).encrypt(iv, html.encode('utf-8'), None)
    b = lambda x: base64.b64encode(x).decode()
    return PAGE.replace('__SALT__', b(salt)).replace('__IV__', b(iv)).replace('__CT__', b(ct)).replace('__IT__', str(IT))

def coz(page, user, pw):
    """Şifreli sayfa (str) -> düz HTML (str). Şifre yanlışsa hata verir."""
    v = dict(re.findall(r"\b(S|IV|CT)='([^']*)'", page)); it = int(re.search(r"\bIT=(\d+)", page).group(1))
    d = base64.b64decode
    return AESGCM(anahtar(user, pw, d(v['S']), it)).decrypt(d(v['IV']), d(v['CT']), None).decode('utf-8')

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--coz':
        user, pw = a[1], a[2]; src = a[3] if len(a) > 3 else 'index.html'; dst = a[4] if len(a) > 4 else 'uygulama_acik.html'
        out = coz(open(src, encoding='utf-8').read(), user, pw)
    else:
        user, pw = a[0], a[1]; src = a[2] if len(a) > 2 else 'uygulama_acik.html'; dst = a[3] if len(a) > 3 else 'index.html'
        out = sifrele(open(src, encoding='utf-8').read(), user, pw)
    open(dst, 'w', encoding='utf-8', newline='\n').write(out)
    print(dst, len(out))
