#!/usr/bin/env python3
"""Read documented public repository GET endpoints; no authentication or access-control bypass.
API documentation: https://colab.mpdl.mpg.de/mediawiki/PubMan_REST_API_Documentation
"""
import io,json,os,zipfile
from pathlib import Path
import repository_followup_v3 as core
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def main():
 results=[]
 r={'n':24,'doi':'10.1016/j.canlet.2024.216985','title':'Colorectal cancer-associated fibroblasts inhibit effector T cells via NECTIN2 signaling'}
 log=[];files=[]
 base='https://pure.mpg.de/rest/items/item_3591858'
 try:
  raw,url,ct=core.get(base,5000000)
  (core.OUT/'metadata'/'24_mpg_public_item.json').write_bytes(raw)
  log.append({'url':url,'bytes':len(raw),'content_type':ct})
 except Exception as e:log.append({'url':base,'error':str(e)[:250]})
 core.inspect(r,base+'/component/file_3591859/content',log,files)
 results.append({**r,'files':files,'attempts':log})
 r={'n':8,'doi':'10.1002/jso.27320','title':'Colorectal cancer in young adults'}
 log=[];files=[]
 core.inspect(r,'https://www.mendeley.com/catalogue/df1f3727-d77a-3801-9228-25e1274c6908/',log,files)
 results.append({**r,'files':files,'attempts':log})
 (core.OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 summary={'requested':2,'pdf_candidates':[r['n'] for r in results if any(f['file'].endswith('.pdf') for f in r['files'])]}
 s=io.BytesIO()
 with zipfile.ZipFile(s,'w',zipfile.ZIP_DEFLATED) as z:
  for p in core.OUT.rglob('*'):
   if p.is_file():z.write(p,str(p.relative_to(core.OUT)))
 key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
 cipher=AESGCM(key).encrypt(nonce,s.getvalue(),b'CRC50-V3')
 pub=serialization.load_pem_public_key(core.PUBLIC_KEY)
 wrapped=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
 out=Path('repository_v3_artifact');out.mkdir(exist_ok=True)
 (out/'bundle.key').write_bytes(wrapped);(out/'bundle.aesgcm').write_bytes(nonce+cipher);(out/'summary.json').write_text(json.dumps(summary))
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
