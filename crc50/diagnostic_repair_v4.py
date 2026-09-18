#!/usr/bin/env python3
"""Diagnose public scholarly sources. No credentials, CAPTCHA solving or paywall bypass.
Only encrypted results leave the temporary runner. The private key stays off GitHub.
"""
import concurrent.futures as cf
import io,json,re,time,os,hashlib,zipfile,unicodedata
from pathlib import Path
from urllib.parse import urljoin,quote
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from download import DATA
PUBLIC_KEY=b'''-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAr3/bTPi/wMlumFZ4Qhhu
xKVyKarjROAvw6JzZh0yEsl72G0hkjkjZaIDuDIvur+8duWQYEgoA3OW1lak/fNY
pzxs97foIBLoVfWqacJcHavDociKWUK2zgGYOMW9Ct/EhsgIgzaqNtPyS+g1xVPl
8pePAlnlsb8Gftd3WWJAVS3JGttM+uwK7zHtGxALFpxXHMOD+id9qEm2r5onieo5
IKFs8OlLLoVmccGR+QPCKxv1F180vvsspOIOBYPVJDAbRR+DKRFfgUdaBIoPhXjK
/sNRKCb69Kg4/RsscFNxm5tXCIwbcZKGpG9s5xRA17pDR+2IYkbc3M1MWRsLOAuQ
gQIDAQAB
-----END PUBLIC KEY-----'''
MISSING={2,3,4,5,7,8,12,14,18,19,22,26,27,28,29,32,33,35,36,37,38,40,42,44,46,48,49,50}
OUT=Path('repair_v4');OUT.mkdir(exist_ok=True)
(OUT/'PDFs').mkdir(exist_ok=True)
(OUT/'HTML').mkdir(exist_ok=True)
REPO={5:'https://inrepo02.dkfz.de/record/276404',27:'https://researchnow.flinders.edu.au/en/publications/metastatic-colorectal-cancer-third-line-therapy-and-beyond/',35:'https://iris.uniroma1.it/handle/11573/1745071'}
PDFS={8:'https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/jso.27320',50:'https://karger.com/dig/article-pdf/106/2/122/4271927/000540594.pdf'}
def norm(s):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(s)).lower())
def inspect(rec,url,session):
    log={'url':url};links=[]
    try:
        r=session.get(url,timeout=(10,30),allow_redirects=True)
        log.update(status=r.status_code,resolved_url=r.url,bytes=len(r.content),content_type=r.headers.get('Content-Type',''),redirects=[{'status':h.status_code,'url':h.url,'location':h.headers.get('Location','')} for h in r.history])
        if r.status_code in (401,403,429):
            soup=BeautifulSoup(r.text,'html.parser');log['title']=soup.title.get_text(' ',strip=True) if soup.title else ''
            log['cause']='rate_limit' if r.status_code==429 else 'access_denied_not_proof_of_subscription'
            return log,links,None
        r.raise_for_status()
        if r.content.startswith(b'%PDF-'):
            reader=PdfReader(io.BytesIO(r.content),strict=False)
            text='\n'.join(p.extract_text() or '' for p in reader.pages[:3]);ntext=norm(text)
            doi_ok=norm(rec['doi']) in ntext;title_ok=norm(rec['title']) in ntext
            if not doi_ok or (len(norm(rec['title']))>28 and not title_ok):
                log['cause']='pdf_identity_not_verified';return log,links,None
            rel=f"PDFs/{rec['n']:02d}_original.pdf";(OUT/rel).write_bytes(r.content)
            f={'file':rel,'n':rec['n'],'doi':rec['doi'],'pages':len(reader.pages),'bytes':len(r.content),'sha256':hashlib.sha256(r.content).hexdigest(),'source_url':r.url,'version':'original_pdf_pending_version_review'}
            log['cause']='pdf_downloaded';return log,links,f
        soup=BeautifulSoup(r.content,'html.parser');text=soup.get_text(' ',strip=True)
        log['title']=soup.title.get_text(' ',strip=True) if soup.title else ''
        log['text_characters']=len(text)
        log['headings']=[h.get_text(' ',strip=True) for h in soup.select('h1,h2,h3')][:24]
        clues=['preview of subscription content','Log in via an institution','Purchase PDF','Purchase access','Buy article','Institutional Login','Get Access','Sign in to view','Performing security verification','Just a moment','Access through your organization','Access through your institution']
        log['access_markers']=[x for x in clues if x.lower() in text.lower()]
        if 'linkinghub.elsevier.com' in r.url:
            pii=re.search(r'/pii/([A-Za-z0-9]+)',r.url)
            if pii:links.append('https://www.sciencedirect.com/science/article/pii/'+pii.group(1))
            log['cause']='doi_intermediary_not_fulltext'
        elif any(x in log['access_markers'] for x in ['preview of subscription content','Purchase access','Buy article','Access through your organization','Access through your institution']):log['cause']='subscription_or_access_gate_seen'
        elif any(x in text.lower() for x in ['performing security verification','verify you are human']):log['cause']='browser_verification'
        else:log['cause']='html_metadata_or_unverified_fulltext'
        for m in soup.select('meta[name="citation_pdf_url"]'):
            if m.get('content'):links.append(urljoin(r.url,m['content']))
        if rec['n'] in (5,27,35):
            for a in soup.find_all('a',href=True):
                u=urljoin(r.url,a['href'])
                if any(x in u for x in ['.pdf','/bitstream/','/server/api/core/bitstreams/','/files/']):links.append(u)
        # Save an unchanged OA HTML response only when article identity, main body and references are present.
        if rec['n']==8 and norm(rec['doi']) in norm(text) and all(s in text.upper() for s in ['EPIDEMIOLOGY','UNIQUE CARE CONSIDERATIONS','REFERENCES']) and len(text)>16000 and 'NonCommercial-NoDerivs' in text:
            rel='HTML/08_publisher_fulltext.html';(OUT/rel).write_bytes(r.content)
            return log,links,{'file':rel,'n':8,'doi':rec['doi'],'source_url':r.url,'version':'publisher_HTML_raw','sha256':hashlib.sha256(r.content).hexdigest(),'bytes':len(r.content)}
        return log,list(dict.fromkeys(links)),None
    except Exception as e:log['cause']='request_error';log['error']=str(e)[:240];return log,links,None

def run(rec):
    s=requests.Session();s.headers['User-Agent']='CRC50-Personal-Literature-Retrieval/4.0'
    queue=['https://doi.org/'+rec['doi']]
    if rec['n'] in PDFS:queue.append(PDFS[rec['n']])
    if rec['n']==8:queue.insert(0,'https://onlinelibrary.wiley.com/doi/full/'+rec['doi'])
    if rec['n'] in REPO:queue.append(REPO[rec['n']])
    # Public Elsevier API requested in FULL view; an API access error is logged, never bypassed.
    if rec['n']==35:
        queue.extend(['https://api.elsevier.com/content/article/pii/S0304419X25001817?view=FULL&httpAccept=application%2Fpdf','https://api.elsevier.com/content/article/pii/S0304419X25001817?view=FULL&httpAccept=text%2Fxml'])
    attempts=[];files=[];seen=set()
    while queue and len(seen)<5:
        url=queue.pop(0)
        if url in seen or not url.startswith('https://'):continue
        seen.add(url);log,links,f=inspect(rec,url,s);attempts.append(log)
        if f:files.append(f);break
        queue.extend(u for u in links if u not in seen)
        time.sleep(0.75)
    print(f"{rec['n']:02d} files={len(files)} causes="+','.join(a['cause'] for a in attempts),flush=True)
    return {**rec,'files':files,'attempts':attempts}
records=[]
for line in DATA.splitlines():
    n,doi,pmid,pmcid,title=line.split('|',4)
    if int(n) in MISSING:records.append({'n':int(n),'doi':doi,'pmid':pmid,'title':title})
with cf.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,records))
(OUT/'diagnostics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
summary={'examined':len(results),'new_files':[f for r in results for f in r['files']]}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
    for p in OUT.rglob('*'):
        if p.is_file():z.write(p,str(p.relative_to(OUT)))
key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
wrapped=serialization.load_pem_public_key(PUBLIC_KEY).encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
a=Path('repair_v4_artifact');a.mkdir(exist_ok=True)
(a/'bundle.aesgcm').write_bytes(nonce+AESGCM(key).encrypt(nonce,buf.getvalue(),b'CRC50-REPAIR-V4'))
(a/'bundle.key').write_bytes(wrapped)
(a/'summary.json').write_text(json.dumps(summary,indent=2))
print('Completed '+json.dumps(summary),flush=True)
