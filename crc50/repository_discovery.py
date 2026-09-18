#!/usr/bin/env python3
import concurrent.futures as cf,json,re,time,threading
from pathlib import Path
from urllib.parse import quote,urlencode,urljoin,urlparse
from bs4 import BeautifulSoup
import requests
import deep_retrieval as base
import download as d
OUT=Path('repository_result');OUT.mkdir(exist_ok=True)
for x in ['PDFs','metadata','pages']:(OUT/x).mkdir(exist_ok=True)
base.OUT=OUT;d.OUT=OUT
RESULTS=[]

def strings(x):
    if isinstance(x,str):yield x
    elif isinstance(x,dict):
        for v in x.values():yield from strings(v)
    elif isinstance(x,list):
        for v in x:yield from strings(v)

def task(r):
    attempts=[];urls=[];seen=set();good=None
    for name,url in [('openaire','https://api.openaire.eu/search/publications?'+urlencode({'doi':r['doi'],'format':'json','size':5})),('s2','https://api.semanticscholar.org/graph/v1/paper/DOI:'+quote(r['doi'],safe='/')+'?fields=title,externalIds,openAccessPdf')]:
        try:
            raw,_=d.get(url,6000000);j=json.loads(raw);(OUT/'metadata'/('%02d_%s.json'%(r['n'],name))).write_bytes(raw)
            if name=='s2':
                u=(j.get('openAccessPdf') or {}).get('url')
                if u:urls.append(u)
            else:
                for u in strings(j):
                    if u.startswith('https://') and not any(s in u for s in ['doi.org/','orcid.org/','api.openaire.eu','openaire.eu/','pubmed.ncbi.nlm.nih.gov']):urls.append(u)
        except Exception as e:attempts.append({'stage':name,'error':str(e)[:200]})
    if r['n']==27:urls.append('https://researchnow.flinders.edu.au/en/publications/metastatic-colorectal-cancer-third-line-therapy-and-beyond/')
    if r['n']==32:urls.append('https://api.nva.unit.no/search/resources?query='+quote(r['doi']))
    if r['n']==50:urls.append('https://www.karger.com/Article/Pdf/540594')
    if r['n']==24:urls.extend(['https://api.elsevier.com/content/article/doi/10.1016/j.canlet.2024.216985?httpAccept=application/pdf','https://www.miltenyibiotec.com/US-en/resources/macs-handbook/research-areas/oncology/colorectal-cancer.html'])
    if r['n']==35:urls.append('https://api.elsevier.com/content/article/doi/10.1016/j.bbcan.2025.189439?httpAccept=application/pdf')
    unique=list(dict.fromkeys(urls));i=0
    while i<len(unique) and len(seen)<12:
        u=unique[i];i+=1
        if u in seen or any(s in u for s in ['ncbi.nlm.nih.gov','europepmc.org','scopus.com','semanticscholar.org','openalex.org']):continue
        seen.add(u)
        try:
            raw,final=d.get(u,85000000)
            if raw.startswith(b'%PDF-'):
                good=d.check_save(r,{'url':u,'version':'repository_version_to_verify'});break
            h=raw.decode('utf-8','replace');s=BeautifulSoup(h,'html.parser')
            if d.norm(r['doi']) not in d.norm(h) and d.norm(r['title']) not in d.norm(h):continue
            path='pages/%02d_%02d.html'%(r['n'],len(seen));(OUT/path).write_bytes(raw)
            found=[]
            for m in s.select('meta[name="citation_pdf_url"]'):
                if m.get('content'):found.append(urljoin(final,m['content']))
            for a in s.find_all('a',href=True):
                href=urljoin(final,a['href']);t=a.get_text(' ',strip=True).lower()
                if any(x in href for x in ['.pdf','/bitstream/','/retrieve/','/files/']) or t in ['download','full text','pdf']:found.append(href)
            found=[x for x in dict.fromkeys(found) if x.startswith('https://')][:8]
            unique.extend(x for x in found if x not in unique)
            attempts.append(dict(url=u,page=path,pdf_candidates=found,status='candidate_not_counted_as_fulltext'))
        except Exception as e:attempts.append(dict(url=u,error=str(e)[:200]))
    return {**r,'result':good,'status':'downloaded' if good else 'not_downloaded','discovered_urls':list(dict.fromkeys(urls)),'attempts':attempts}

with cf.ThreadPoolExecutor(max_workers=3) as pool:
    for r in pool.map(task,base.RECORDS):
        RESULTS.append(r);print('REPOSITORY',r['n'],r['status'],flush=True)
        (OUT/'results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2))
base.pkg({'requested':len(RESULTS),'downloaded':[r['n'] for r in RESULTS if r['status']=='downloaded'],'missing':[r['n'] for r in RESULTS if r['status']!='downloaded']})
