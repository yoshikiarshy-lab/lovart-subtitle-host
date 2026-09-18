#!/usr/bin/env python3
"""Bounded public-source retrieval. No login, paywall, CAPTCHA bypass or proxy.
All returned files require local identity/fullness review. No PDFs are committed.
"""
import ast, concurrent.futures as cf, hashlib, io, json, os, re, time, zipfile
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlparse
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
PUBLIC_KEY=b'''-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAr6ASe9/PFJzVWyg5ePhi
fVnzgKHZFDJQhcwVF0cs86Q/mlGV60K1POfVWoegtsp83+ezvIGYwvNo8rH7EkZX
k6YvlM5qVqNF+RxnUxvmP6IXYdYrLnJNuNj1Ky74gDYq+CFv7fPM8nwdMbv7Ae0s
nq5pgQNP0qbJpBun71/rkH5q85hifydhClMmPV+ftDnjvrmWbDw5/CvIT+sHQ650
RZlpIbj4SlWAvJuU/FO9B2I2tcuuJmX68x5qdYr9qUiTGtUSPZwxwYzAI0oqHhIr
SCTdjvmICLG6tpV/rqcN/dngWzzIkafnVrxQJIOgZwovbtO24EJuLhxYLPFm4JK9
AvXyhSzkXJGeRi7yng3D0uDMB46SBtuc1Dk05tY8iTlL2uTsnBkp42wCFsKBiUAJ
HQJQzcpyXgPeT1vUKGjfGi11kE1xCa/AnLeQE0aZhUkS8WFS4FgH3uGOr+PznOMH
/wU9rySfvO35E/k9nQxJWpyrsFF1BdF9RprpiN0fn97NAgMBAAE=
-----END PUBLIC KEY-----'''
MISSING={2,3,4,5,7,8,12,14,18,19,22,24,26,27,28,29,32,33,35,36,37,38,40,42,44,46,48,49,50}
OUT=Path('repository_v3_result');OUT.mkdir(exist_ok=True)
for x in ['PDFs','HTML_candidates','XML_candidates','metadata']:(OUT/x).mkdir(exist_ok=True)
START=time.time()
def norm(x):return re.sub('[^a-z0-9]','',str(x).lower())
def get(url,limit=55000000):
 if not url.startswith('https://'):raise ValueError('Public HTTPS only')
 with requests.get(url,headers={'User-Agent':'Research-Article-Retriever/1.0'},timeout=(6,18),stream=True) as r:
  r.raise_for_status(); raw=bytearray()
  for b in r.iter_content(65536):
   raw.extend(b)
   if len(raw)>limit:raise ValueError('Size limit')
  return bytes(raw),r.url,r.headers.get('Content-Type','')
def walk_urls(obj):
 out=[]
 if isinstance(obj,dict):
  for v in obj.values():out+=walk_urls(v)
 elif isinstance(obj,list):
  for v in obj:out+=walk_urls(v)
 elif isinstance(obj,str) and obj.startswith('https://'):out.append(obj)
 return out

def inspect(r,url,log,files,depth=0):
 if time.time()-START>300:return
 try:
  raw,final,ct=get(url)
  item={'url':url,'resolved_url':final,'bytes':len(raw),'content_type':ct}
  log.append(item)
  if raw.startswith(b'%PDF-'):
   reader=PdfReader(io.BytesIO(raw));p=len(reader.pages)
   txt=' '.join(reader.pages[i].extract_text() or '' for i in range(min(p,3)))
   if norm(r['doi']) not in norm(txt) and (len(norm(r['title']))<28 or norm(r['title']) not in norm(txt)):
    item['status']='wrong_identity';return
   if b'%%EOF' not in raw[-20000:]:raise ValueError('PDF incomplete')
   path=f"PDFs/{r['n']:02d}_source_{hashlib.sha256(raw).hexdigest()[:10]}.pdf"
   (OUT/path).write_bytes(raw)
   files.append({'file':path,'pages':p,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source_url':final,'doi':r['doi'],'n':r['n'],'version':'source_version_pending_local_review'})
   item['status']='pdf_identity_matched';print('PDF',r['n'],p,flush=True);return
  if 'xml' in ct or raw.lstrip().startswith(b'<?xml'):
   try:
    root=ET.fromstring(raw);text=' '.join(root.itertext())
    sections=sum(1 for e in root.iter() if e.tag.split('}')[-1] in ('section','sec'))
    if norm(r['doi']) in norm(text) and sections>=3 and len(text)>15000:
     path=f"XML_candidates/{r['n']:02d}_fulltext_candidate.xml";(OUT/path).write_bytes(raw)
     files.append({'file':path,'bytes':len(raw),'sections':sections,'source_url':final,'n':r['n'],'version':'fulltext_XML_pending_local_review'});item['status']='xml_candidate'
   except ET.ParseError:pass
   return
  soup=BeautifulSoup(raw,'html.parser')
  for t in soup(['script','style','noscript']):t.decompose()
  text=soup.get_text(' ',strip=True)
  if norm(r['doi']) not in norm(text):item['status']='no_target_identity';return
  item['text_characters']=len(text)
  item['headings']=[h.get_text(' ',strip=True) for h in soup.select('h1,h2,h3')][:50]
  # Save original public HTML only for later review, never call it full text here.
  if len(text)>7000:
   path=f"HTML_candidates/{r['n']:02d}_{hashlib.sha256(url.encode()).hexdigest()[:8]}.html"
   (OUT/path).write_bytes(raw);item['candidate_path']=path
  if depth<1:
   links=[]
   for m in soup.select('meta[name="citation_pdf_url"]'):
    if m.get('content'):links.append(urljoin(final,m['content']))
   for a in soup.select('a[href]'):
    h=a['href'];label=a.get_text(' ',strip=True).lower()
    if '.pdf' in h.lower() or '/bitstream/' in h or '/bitstreams/' in h or ('download' in label and 'pdf' in label):links.append(urljoin(final,h))
   item['file_links']=list(dict.fromkeys(links))[:6]
   for link in item['file_links']:
    if link!=url and link.startswith('https://'):inspect(r,link,log,files,depth+1)
  item.setdefault('status','html_only_not_counted')
 except Exception as e:log.append({'url':url,'error':str(e)[:180]})

EXTRA={
 8:['https://onlinelibrary.wiley.com/doi/abs/10.1002/jso.27320'],
 24:['https://publications.goettingen-research-online.de/handle/2/144096','https://api.elsevier.com/content/article/pii/S0304383524003793?httpAccept=text%2Fxml'],
 27:['https://researchnow.flinders.edu.au/en/publications/metastatic-colorectal-cancer-third-line-therapy-and-beyond/'],
 35:['https://iris.uniroma1.it/handle/11573/1745071','https://api.elsevier.com/content/article/pii/S0304419X25001817?httpAccept=text%2Fxml'],
 46:['https://digitalcommons.lib.uconn.edu/do/search/?q=%22116393%22&start=0&context=all'],
}

def run(r):
 log=[];files=[];candidates=list(EXTRA.get(r['n'],[]))
 # Search repository aggregators for author-deposited copies rather than retrying paywalls.
 endpoints=[('hal','https://api.archives-ouvertes.fr/search/?'+urlencode({'q':'doiId_s:"'+r['doi']+'"','fl':'title_s,doiId_s,fileMain_s,uri_s,files_s,docType_s','wt':'json','rows':5})),('openaire','https://api.openaire.eu/search/publications?'+urlencode({'doi':r['doi'],'format':'json','size':5}))]
 for label,url in endpoints:
  if time.time()-START>250:break
  try:
   raw,final,ct=get(url,12000000);obj=json.loads(raw)
   (OUT/'metadata'/f"{r['n']:02d}_{label}.json").write_bytes(raw)
   if label=='hal':
    for d in obj.get('response',{}).get('docs',[]):
     for k in ['fileMain_s','uri_s']:
      if d.get(k):candidates.append(d[k])
   else:
    for u in walk_urls(obj):
     host=urlparse(u).netloc.lower()
     # Avoid identifier-only pages; inspect repository links and direct PDFs.
     if any(x in host for x in ['doi.org','pubmed','orcid.org','crossref.org','creativecommons.org','openaire.eu']):continue
     if '.pdf' in u.lower() or any(x in u.lower() for x in ['handle','repository','repositorio','eprints','hal.science','zenodo','figshare','digitalcommons','pure.mpg']):candidates.append(u)
   log.append({'metadata_source':label,'candidate_count':len(candidates)})
  except Exception as e:log.append({'metadata_source':label,'error':str(e)[:180]})
 for u in list(dict.fromkeys(candidates))[:8]:
  if files or time.time()-START>300:break
  inspect(r,u,log,files)
 return {**r,'files':files,'attempts':log,'status':'retrieved_pending_review' if files else 'not_downloaded'}

def main():
 tree=ast.parse(Path('crc50/download.py').read_text())
 data=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DATA' for t in n.targets))
 records=[]
 for line in data.splitlines():
  n,doi,pmid,pmcid,title=line.split('|',4)
  if int(n) in MISSING:records.append({'n':int(n),'doi':doi,'title':title,'pmid':pmid})
 results=[]
 with cf.ThreadPoolExecutor(max_workers=4) as p:
  for r in p.map(run,records):results.append(r)
 (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 summary={'requested':len(records),'pdf_candidates':[r['n'] for r in results if any(f['file'].endswith('.pdf') for f in r['files'])],'other_candidates':[r['n'] for r in results if any(not f['file'].endswith('.pdf') for f in r['files'])],'elapsed_seconds':round(time.time()-START)}
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  for f in OUT.rglob('*'):
   if f.is_file():z.write(f,str(f.relative_to(OUT)))
 key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
 cipher=AESGCM(key).encrypt(nonce,stream.getvalue(),b'CRC50-V3')
 public=serialization.load_pem_public_key(PUBLIC_KEY)
 wrapped=public.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
 a=Path('repository_v3_artifact');a.mkdir(exist_ok=True)
 (a/'bundle.aesgcm').write_bytes(nonce+cipher);(a/'bundle.key').write_bytes(wrapped);(a/'summary.json').write_text(json.dumps(summary))
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
