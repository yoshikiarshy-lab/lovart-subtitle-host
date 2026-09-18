#!/usr/bin/env python3
"""Bounded additional public scholarly retrieval. No authentication or paywall bypass."""
import download as d
import json, io, os, re, time, hashlib, zipfile, concurrent.futures as cf
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlparse
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MISSING={1,2,3,4,5,6,7,8,9,12,14,18,19,22,24,26,27,28,29,32,33,34,35,36,37,38,40,42,44,46,48,49,50}
RECORDS=[]
for line in d.DATA.splitlines():
    n,doi,pmid,pmcid,title=line.split('|',4)
    if int(n) in MISSING: RECORDS.append(dict(n=int(n),doi=doi,pmid=pmid,pmcid=pmcid,title=title))
OUT=Path('deep_result');OUT.mkdir(exist_ok=True)
for f in ['PDFs','metadata','candidate_pages']:(OUT/f).mkdir(exist_ok=True)
d.OUT=OUT
DIRECT={
1:['https://europepmc.org/articles/PMC10365888?pdf=render','https://pmc.ncbi.nlm.nih.gov/articles/PMC10365888/pdf/nihms-1915339.pdf'],
6:['https://europepmc.org/articles/PMC9924026?pdf=render','https://pmc.ncbi.nlm.nih.gov/articles/PMC9924026/pdf/nihms-1864616.pdf'],
34:['https://europepmc.org/articles/PMC8968072?pdf=render','https://pmc.ncbi.nlm.nih.gov/articles/PMC8968072/pdf/nihms-1784007.pdf'],
8:['https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/jso.27320','https://onlinelibrary.wiley.com/doi/pdf/10.1002/jso.27320','https://onlinelibrary.wiley.com/doi/abs/10.1002/jso.27320'],
24:['https://www.sciencedirect.com/science/article/pii/S0304383524003793/pdfft','https://www.sciencedirect.com/science/article/pii/S0304383524003793'],
35:['https://www.sciencedirect.com/science/article/pii/S0304419X25001817/pdfft','https://www.sciencedirect.com/science/article/pii/S0304419X25001817'],
36:['https://www.sciencedirect.com/science/article/pii/S2210740122001176','https://www.em-consulte.com/article/1553300/msi-colorectal-cancer-all-you-need-to-know'],
50:['https://karger.com/dig/article-pdf/106/2/122/4271927/000540594.pdf','https://karger.com/dig/article/106/2/122/911780/Management-of-T1-Colorectal-Cancer'],
32:['https://evidence.nejm.org/doi/pdf/10.1056/EVIDra2100035'],
38:['https://www.nature.com/articles/s41568-021-00432-3.pdf']}

def pkg(summary):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(OUT)))
    key=AESGCM.generate_key(bit_length=256); nonce=os.urandom(12)
    pub=serialization.load_pem_public_key(Path('crc50/deep_public_key.pem').read_bytes())
    dest=Path('deep_artifact');dest.mkdir(exist_ok=True)
    (dest/'bundle.aesgcm').write_bytes(nonce+AESGCM(key).encrypt(nonce,b.getvalue(),b'CRC50-DEEP-20260918'))
    (dest/'bundle.key').write_bytes(pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)))
    (dest/'summary.json').write_text(json.dumps(summary,indent=2))

def getmeta(r,tag,url,errors):
    try:
        raw,_=d.get(url,15000000)
        j=json.loads(raw)
        (OUT/'metadata'/('%02d_%s.json'%(r['n'],tag))).write_bytes(raw)
        return j
    except Exception as e:errors.append(dict(stage=tag,url=url,error=str(e)[:220]));return {}

def work(r):
    errors=[];candidates=[];locs=[];seen=set();saved=None;start=time.monotonic()
    def add(u,version='public_version_to_verify',context=''):
        if not u:return
        if u.startswith('http://'):u='https://'+u[7:]
        if urlparse(u).scheme!='https':return
        candidates.append(dict(url=u,version=version,context=context))
    # Resolve up-to-date repository locations using independent public metadata.
    oa=getmeta(r,'openalex','https://api.openalex.org/works/https://doi.org/'+quote(r['doi'],safe='/'),errors)
    for l in oa.get('locations',[]):
        locs.append({k:l.get(k) for k in ['landing_page_url','pdf_url','is_oa','version','license']})
        if l.get('pdf_url'):add(l['pdf_url'],l.get('version') or 'repository_version',l.get('license') or '')
        u=l.get('landing_page_url') or ''
        if u and not any(x in u for x in ['pubmed.ncbi.nlm.nih.gov','doi.org/']):add(u,l.get('version') or 'repository_version',l.get('license') or '')
    ep=getmeta(r,'europepmc','https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode(dict(query='EXT_ID:'+r['pmid']+' AND SRC:MED',format='json',resultType='core',pageSize=1)),errors)
    for e in ep.get('resultList',{}).get('result',[]):
        for l in e.get('fullTextUrlList',{}).get('fullTextUrl',[]):
            if l.get('availabilityCode') in ['OA','F']:add(l.get('url'),'public_fulltext',l.get('documentStyle',''))
        if e.get('pmcid') and not r['pmcid']:r['pmcid']=e['pmcid'];add('https://europepmc.org/articles/'+e['pmcid']+'?pdf=render','accepted_manuscript')
    cr=getmeta(r,'crossref','https://api.crossref.org/works/'+quote(r['doi'],safe=''),errors).get('message',{})
    for l in cr.get('link',[]):
        if l.get('content-type')=='application/pdf':add(l.get('URL'),'publisher_PDF','Crossref PDF link')
    if r['n']==36:
        hal=getmeta(r,'hal','https://api.archives-ouvertes.fr/search/?'+urlencode(dict(q='doiId_s:"'+r['doi']+'"',wt='json',fl='title_s,doiId_s,uri_s,fileMain_s,files_s,docType_s,version_i',rows=10)),errors)
        for l in hal.get('response',{}).get('docs',[]):
            add(l.get('fileMain_s'),'accepted_manuscript','HAL repository')
            add(l.get('uri_s'),'accepted_manuscript','HAL repository')
    for u in DIRECT.get(r['n'],[]):add(u,'accepted_manuscript' if r['n'] in [1,6,34] else 'publisher_PDF','Direct public source')
    if r['doi'].startswith('10.1007/'):add('https://link.springer.com/content/pdf/'+r['doi']+'.pdf','publisher_PDF')
    if r['doi'].startswith('10.1080/'):add('https://www.tandfonline.com/doi/pdf/'+r['doi'],'publisher_PDF')
    if r['doi'].startswith('10.1002/'):add('https://onlinelibrary.wiley.com/doi/pdfdirect/'+r['doi'],'publisher_PDF')
    if r['doi'].startswith('10.1055/'):add('https://www.thieme-connect.com/products/ejournals/pdf/'+r['doi']+'.pdf','publisher_PDF')
    add('https://doi.org/'+r['doi'],'publisher_version')
    i=0
    while i<len(candidates) and len(seen)<18 and time.monotonic()-start<180:
        s=candidates[i];i+=1;u=s['url']
        if u in seen:continue
        seen.add(u)
        try:
            raw,final=d.get(u,85000000)
            if raw.startswith(b'%PDF-'):
                # Reuse strict identity, parseability and complete PDF checks.
                result=d.check_save(r,s);saved=result;break
            h=raw.decode('utf-8','replace')
            if d.norm(r['doi']) not in d.norm(h) and d.norm(r['title']) not in d.norm(h):
                errors.append(dict(url=u,status='not_target_fulltext_or_access_barrier',bytes=len(raw)));continue
            soup=BeautifulSoup(h,'html.parser')
            page_name='%02d_%s.html'%(r['n'],hashlib.sha256(u.encode()).hexdigest()[:10])
            (OUT/'candidate_pages'/page_name).write_bytes(raw)
            found=[]
            for m in soup.select('meta[name="citation_pdf_url"]'):
                if m.get('content'):found.append(urljoin(final,m['content']))
            for a in soup.find_all('a',href=True):
                href=urljoin(final,a['href']);label=a.get_text(' ',strip=True).lower()
                if any(t in href.lower() for t in ['/retrieve/','/bitstream/','/file/','/document','/pdfft','.pdf','?pdf=render']) or label in ['pdf','download pdf','view open manuscript','full text','download']:
                    if href.startswith('https://') and len(found)<12:found.append(href)
            for href in dict.fromkeys(found):
                if href not in seen:add(href,s['version'],final)
            errors.append(dict(url=u,resolved_url=final,status='html_candidate_saved_not_counted_as_fulltext',file='candidate_pages/'+page_name,bytes=len(raw),pdf_links=found))
        except Exception as e:errors.append(dict(url=u,error=str(e)[:250]))
    return {**r,'status':'downloaded' if saved else 'not_downloaded','result':saved,'locations':locs,'attempts':errors,'candidate_count':len(candidates)}

if __name__=='__main__':
    results=[]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(work,r):r for r in RECORDS}
        for f in cf.as_completed(futures):
            try:res=f.result()
            except Exception as e:res={**futures[f],'status':'error','error':str(e)}
            results.append(res);print('RESULT',res['n'],res['status'],flush=True)
            (OUT/'results.json').write_text(json.dumps(sorted(results,key=lambda x:x['n']),ensure_ascii=False,indent=2))
    summary={'requested':len(results),'downloaded':[r['n'] for r in results if r['status']=='downloaded'],'missing':[r['n'] for r in results if r['status']!='downloaded']}
    pkg(summary);print(json.dumps(summary),flush=True)
