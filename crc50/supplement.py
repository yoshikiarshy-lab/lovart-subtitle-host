#!/usr/bin/env python3
"""Targeted second pass: public original files only; preserve source versions."""
import download as d
import json,re,html,hashlib
from urllib.parse import urljoin,quote,unquote,urlparse
from xml.etree import ElementTree as ET
from pathlib import Path
from html.parser import HTMLParser

TARGET={1,5,6,8,9,17,24,31,34,35,36,50}
d.DATA='\n'.join(s for s in d.DATA.splitlines() if int(s.split('|',1)[0]) in TARGET)
DIRECT={
1:[('https://pmc.ncbi.nlm.nih.gov/articles/PMC10365888/pdf/nihms-1915339.pdf','accepted_manuscript'),('https://europepmc.org/articles/PMC10365888?pdf=render','accepted_manuscript')],
6:[('https://pmc.ncbi.nlm.nih.gov/articles/PMC9924026/pdf/nihms-1864616.pdf','accepted_manuscript'),('https://europepmc.org/articles/PMC9924026?pdf=render','accepted_manuscript')],
9:[('https://iris.unito.it/retrieve/99802604-dc9d-4472-b5c4-26537c970f68/2025-Tumor%20age_preprint.pdf','preprint_NOT_final')],
17:[('https://ddfv.ufv.es/bitstreams/d586cdcf-056c-4083-b84e-50bd2002b268/download','repository_version_to_verify')],
34:[('https://pmc.ncbi.nlm.nih.gov/articles/PMC8968072/pdf/nihms-1787436.pdf','accepted_manuscript'),('https://europepmc.org/articles/PMC8968072?pdf=render','accepted_manuscript')]
}
LANDINGS={
5:['https://inrepo02.dkfz.de/record/276404'],
8:['https://onlinelibrary.wiley.com/doi/abs/10.1002/jso.27320'],
17:['https://www.sciencedirect.com/science/article/pii/S1040842823001555'],
24:['https://resolver.sub.uni-goettingen.de/purl?gro-2/144096','https://publications.goettingen-research-online.de/handle/2/144096','https://www.sciencedirect.com/science/article/pii/S0304383524003793'],
31:['https://hdl.handle.net/10871/133490','https://www.sciencedirect.com/science/article/pii/S1521691823000227'],
35:['https://iris.uniroma1.it/handle/11573/1745071','https://www.sciencedirect.com/science/article/pii/S0304419X25001817'],
36:['https://www.em-consulte.com/article/1553300/figures/msi-colorectal-cancer-all-you-need-to-know'],
50:['https://karger.com/dig/article/106/2/122/911059/Management-of-T1-Colorectal-Cancer']
}
class Links(HTMLParser):
 def __init__(self):super().__init__();self.urls=[];self.meta=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag.lower()=='a' and a.get('href'):self.urls.append(a['href'])
  if tag.lower()=='meta' and a.get('name','').lower()=='citation_pdf_url':self.meta.append(a.get('content',''))

def retrieve(r):
 attempts=[];seen=set();source_html=[]
 def try_pdf(url,version,origin=''):
  if url in seen:return None
  seen.add(url)
  try:
   v=d.check_save(r,{'url':url,'version':version,'metadata_url':origin})
   if version=='preprint_NOT_final':
    old=d.OUT/v['file']; new=d.OUT/'PREPRINT_NOT_FINAL'/old.name;new.parent.mkdir(exist_ok=True);old.rename(new);v['file']=str(new.relative_to(d.OUT));v['status']='preprint_only'
   v['attempts']=attempts;print('SUPPLEMENT_SAVED',r['n'],v['pages'],version,flush=True);return v
  except Exception as e:attempts.append({'url':url,'error':str(e)[:250]})
 for url,ver in DIRECT.get(r['n'],[]):
  v=try_pdf(url,ver)
  if v:return v
 if r['n']==31:
  try:
   u='https://api.figshare.com/v2/articles/29796620';raw,_=d.get(u,4000000);meta=json.loads(raw)
   (d.OUT/'source_metadata'/'31_figshare.json').write_bytes(raw)
   if 'symptomatic patients' in meta.get('title','').lower():
    for f in meta.get('files',[]):
     v=try_pdf(f['download_url'],'repository_version_to_verify',u)
     if v:return v
  except Exception as e:attempts.append({'stage':'figshare','error':str(e)[:250]})
 for landing in LANDINGS.get(r['n'],[]):
  try:
   raw,final=d.get(landing,10000000)
   if raw.startswith(b'%PDF-'):
    v=try_pdf(final,'repository_version_to_verify',landing)
    if v:return v
    continue
   text=raw.decode('utf-8','replace')
   fn='%02d_landing_%d.html'%(r['n'],len(source_html)); (d.OUT/'source_metadata'/fn).write_bytes(raw);source_html.append(fn)
   if d.norm(r['doi']) not in d.norm(unquote(text)) and d.norm(r['title']) not in d.norm(text):
    attempts.append({'url':landing,'error':'Landing identity not found'});continue
   parser=Links();parser.feed(text)
   urls=parser.meta+[u for u in parser.urls if any(s in u.lower() for s in ('/bitstream','/retrieve/','/pdfft','/article-pdf/','/files/','.pdf'))]
   for url in dict.fromkeys(urls):
    u=urljoin(final,html.unescape(url))
    if urlparse(u).scheme!='https':continue
    if any(x in u.lower() for x in ('supplement','-mmc','-supp','citation','metrics')):continue
    v=try_pdf(u,'repository_version_to_verify' if any(s in landing for s in ('iris.','dkfz.','handle.net','research-online','resolver.')) else 'publisher_PDF',final)
    if v:return v
  except Exception as e:attempts.append({'url':landing,'error':str(e)[:250]})
 # When the official NLM distribution exposes original full-text XML/TXT but no PDF,
 # retain those exact source files, not a generated/reconstructed PDF.
 if r['n'] in (1,6,34):
  try:
   u=d.CLOUD+'metadata/'+r['pmcid']+'.1.json';raw,_=d.get(u,2000000);meta=json.loads(raw)
   if d.norm(meta.get('doi',''))!=d.norm(r['doi']):raise ValueError('PMC metadata DOI mismatch')
   (d.OUT/'source_metadata'/('%02d_pmc.json'%r['n'])).write_bytes(raw)
   saved=[]
   for field,ext in [('xml_url','xml'),('text_url','txt')]:
    if not meta.get(field):continue
    b,final=d.get(meta[field],12000000)
    if ext=='xml':
     root=ET.fromstring(b)
     body=root.find('.//body')
     if body is None or len(''.join(body.itertext()))<3000:raise ValueError('Not full-text XML')
    path='Official_fulltext_XML/%02d_%s.%s'%(r['n'],r['pmcid'],ext)
    (d.OUT/'Official_fulltext_XML').mkdir(exist_ok=True);(d.OUT/path).write_bytes(b)
    saved.append({'file':path,'source_url':meta[field],'resolved_url':final,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
   if saved:
    print('OFFICIAL_FULLTEXT_XML',r['n'],flush=True)
    return {**r,'status':'official_XML_fulltext','version':'accepted_manuscript_XML','license':meta.get('license_code'),'files':saved,'attempts':attempts}
  except Exception as e:attempts.append({'stage':'original_fulltext_XML','error':str(e)[:250]})
 return {**r,'status':'not_downloaded','attempts':attempts,'source_html':source_html}
d.retrieve=retrieve
d.main()
