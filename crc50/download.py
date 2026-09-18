#!/usr/bin/env python3
"""One-time public scholarly PDF retrieval. No credentials or access-control bypass.
Only ciphertext leaves the runner as an artifact; private key is not in this repo.
PMC distribution documentation: https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/
"""
import concurrent.futures as cf
import csv, hashlib, io, json, os, re, threading, time, unicodedata, zipfile
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlparse, parse_qs, unquote
from xml.etree import ElementTree as ET
from html.parser import HTMLParser
import requests
from pypdf import PdfReader
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PUBLIC_KEY = b'''-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAuz5uPksz9MMOPDkdhgS7
HaBNI+ByGL7tppu9Iroi4dybTUz9ep5x5PvqS9lWmoiLGkVmkGYGq1G91uBcHOmo
zB78MIfxaM7QTjhl3gPdcj2Zd2bfnr0u+deuqSv9gHDZ7WoMTVqALr5iGVljXF8F
Ygas2bIMpwhuzg1m8xXPJQGTboRojiMPdDsRpva3mAwhsasTfW0tjmf8wCM4PuPJ
JCpEpuRl4AoEdNzWxnPEUUWb9jaJ58YQilI5p/Qz04K4IJtfHef26Wm/WPNCVyjB
/MPSOCiIO050kgCQVdQc46s3cb4gtIhZm8vF7paisq2UX8nLEJpZzWfTLCB9xwA2
nK0clCAvjAs7gLl0B7RuRZzWMW0+JZrgtIM8PW2BbO18+hCavovc3Rq31kgq793G
n1JNs+SBMrBvANThQdRi4ZW5+T0O81JLGHPuSf+R32I5eKy0IL9Ks5mijvNAF2wa
czMUZ6+uzru9ng+qKklajUrfr8cZsjKBzJI1Dy6/OLctAgMBAAE=
-----END PUBLIC KEY-----'''

DATA = '''1|10.1016/j.tips.2023.01.003|36828759|PMC10365888|Metastatic colorectal cancer: mechanisms and emerging therapeutics
2|10.1016/j.suc.2023.11.009|38677823||Screening for Colorectal Cancer
3|10.1007/s10555-023-10158-3|38112903||Colorectal cancer: a comprehensive review of carcinogenesis, diagnosis, and novel strategies for classified treatments
4|10.1016/j.soc.2021.12.001|35351269||Colorectal Cancer: Preoperative Evaluation and Staging
5|10.1016/j.bpg.2023.101839|37852707||Colorectal cancer: A health and economic problem
6|10.1016/j.giec.2021.12.001|35361330|PMC9924026|Cause, Epidemiology, and Histology of Polyps and Pathways to Colorectal Cancer
7|10.1016/j.hoc.2022.02.002|35577708||Hereditary Colorectal Cancer
8|10.1002/jso.27320|37222697||Colorectal cancer in young adults
9|10.1016/j.cell.2024.12.003|39919707||Tumor age in early-onset colorectal cancer
10|10.3748/wjg.v30.i33.3818|39351429|PMC11438623|Early diagnostic strategies for colorectal cancer
11|10.3390/ijms25179463|39273409|PMC11395697|From Crypts to Cancer: A Holistic Perspective on Colorectal Carcinogenesis and Therapeutic Strategies
12|10.1007/s10354-022-00975-6|36348129||Colorectal cancer
13|10.3389/fimmu.2021.807648|35069592|PMC8777015|Potential Role of the Gut Microbiome In Colorectal Cancer Progression
14|10.1016/j.soc.2021.11.001|35351270||Early-Onset Colorectal Cancer
15|10.32604/or.2025.063951|40612862|PMC12215587|Lynch syndrome and colorectal cancer: A review of current perspectives in molecular genetics and clinical strategies
16|10.1016/j.trecan.2023.11.003|38071119||Plastic persisters: revival stem cells in colorectal cancer
17|10.1016/j.critrevonc.2023.104067|37454703||Dichotomous colorectal cancer behaviour
18|10.1016/j.tcb.2024.08.006|39261152||Gut microbial metabolism in ferroptosis and colorectal cancer
19|10.1016/j.gtc.2022.05.002|36153111||Colorectal Cancer Screening in a Changing World
20|10.3892/or.2025.8963|40776741|PMC12351159|Liver metastasis of colorectal cancer: Mechanism and clinical therapy (Review)
21|10.4166/kjg.2023.083|37621241|PMC12285384|Obesity and Colorectal Cancer
22|10.1055/a-2855-5688|42705241||Colorectal Cancer
23|10.3390/ijms26051988|40076613|PMC11901061|Mechanisms and Strategies to Overcome Drug Resistance in Colorectal Cancer
24|10.1016/j.canlet.2024.216985|38821255||Colorectal cancer-associated fibroblasts inhibit effector T cells via NECTIN2 signaling
25|10.3390/genes15050538|38790167|PMC11120657|Colorectal Cancer: Genetic Underpinning and Molecular Therapeutics for Precision Medicine
26|10.1016/j.crad.2021.09.003|34579868||Colorectal cancer
27|10.1080/14737140.2024.2334784|38526540||Metastatic colorectal cancer- third line therapy and beyond
28|10.1016/j.soc.2021.11.010|35351280||Management of Colorectal Cancer in Hereditary Syndromes
29|10.1007/s00292-026-01562-x|42087013||Hereditary colorectal cancer
30|10.61409/V07250620|41873244||Colorectal cancer recurrence
31|10.1016/j.bpg.2023.101842|37852715||Colorectal cancer in symptomatic patients: How to improve the diagnostic pathway
32|10.1056/EVIDra2100035|38319175||Colorectal Cancer Screening - Approach, Evidence, and Future Directions
33|10.1016/j.giec.2021.08.001|34798987||Colorectal Cancer Screening Recommendations and Outcomes in Lynch Syndrome
34|10.1016/j.soc.2021.11.002|35351271|PMC8968072|Healthcare Disparities and Colorectal Cancer
35|10.1016/j.bbcan.2025.189439|40907725||Colorectal cancer chemoprevention: Exploring the path from molecular mechanisms to available drugs
36|10.1016/j.clinre.2022.101983|35732266||MSI colorectal cancer, all you need to know
37|10.1002/jso.27848|39295552||Colorectal cancer care continuum: Navigating screening, treatment, and outcomes disparities
38|10.1038/s41568-021-00432-3|34880443||Colorectal cancer subtyping
39|10.3389/fimmu.2025.1714954|41346579|PMC12672550|Colorectal cancer stem cells crosstalk in tumor immune microenvironment and targeted therapeutic strategies
40|10.1007/s12032-023-02131-5|37530984||HOTAIR in colorectal cancer: structure, function, and therapeutic potential
41|10.3748/wjg.v30.i33.3810|39351431|PMC11438629|Colorectal cancer cell dormancy: An insight into pathways
42|10.1002/ijc.35425|40181553||Gestational colorectal cancer: Mechanisms, treatments, and prognosis
43|10.3389/fimmu.2026.1861130|42500682|PMC13395994|Colorectal cancer liver metastases: mechanism and therapy
44|10.1016/j.crad.2021.06.002|34281707||Postoperative complications of colorectal cancer
45|10.1093/oncolo/oyae141|38906705|PMC11448877|Fertility in young-onset colorectal patients with cancer: a review
46|10.1016/j.bcp.2024.116393|38942088||Early onset colorectal cancer: Cancer promotion in young tissue
47|10.3748/wjg.v30.i23.2959|38946873|PMC11212702|Early colorectal cancer screening-no time to lose
48|10.1080/14712598.2024.2341744|38644655||The future of cancer vaccines against colorectal cancer
49|10.1016/j.giec.2021.08.002|34798988||Lynch Syndrome-Associated Cancers Beyond Colorectal Cancer
50|10.1159/000540594|39097960||Management of T1 Colorectal Cancer'''
DIRECT = {
  8:['https://onlinelibrary.wiley.com/doi/pdf/10.1002/jso.27320'],
  11:['https://www.mdpi.com/1422-0067/25/17/9463/pdf-vor'],
  13:['https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2021.807648/pdf'],
  15:['https://cdn.techscience.cn/files/or/2025/TSP_OR-33-7/OncolRes-33-07-63951/OncolRes-33-63951.pdf'],
  16:['https://discovery.ucl.ac.uk/id/eprint/10183520/1/1-s2.0-S2405803323002315-main.pdf'],
  20:['https://www.spandidos-publications.com/10.3892/or.2025.8963/download'],
  23:['https://www.mdpi.com/1422-0067/26/5/1988/pdf-vor'],
  25:['https://www.mdpi.com/2073-4425/15/5/538/pdf-vor'],
  30:['https://content.ugeskriftet.dk/sites/default/files/V07250620_WEB.pdf'],
  39:['https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2025.1714954/pdf'],
  43:['https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2026.1861130/pdf'],
  50:['https://karger.com/dig/article-pdf/106/2/122/4271927/000540594.pdf']
}
CLOUD='https://pmc-oa-opendata.s3.amazonaws.com/'
OUT=Path('download_result'); OUT.mkdir(exist_ok=True)
(OUT/'PDFs').mkdir(exist_ok=True)
(OUT/'source_metadata').mkdir(exist_ok=True)
LOCAL=threading.local()

def norm(s):
    return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(s)).lower())

def get(url,limit=85000000):
    if url.startswith('s3://pmc-oa-opendata/'):
        url=CLOUD+url.split('s3://pmc-oa-opendata/',1)[1]
    if urlparse(url).scheme!='https': raise ValueError('Only HTTPS public sources')
    if not hasattr(LOCAL,'session'):
        LOCAL.session=requests.Session()
        LOCAL.session.headers.update({'User-Agent':'CRC50-Research-PDF-Retriever/1.1','Accept':'*/*'})
    with LOCAL.session.get(url,timeout=(8,25),stream=True) as r:
        r.raise_for_status()
        chunks=[]; size=0
        for chunk in r.iter_content(65536):
            size+=len(chunk)
            if size>limit: raise ValueError('File exceeds size limit')
            chunks.append(chunk)
        return b''.join(chunks),r.url

class Metadata(HTMLParser):
    def __init__(self): super().__init__(); self.urls=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag.lower()=='meta' and (a.get('name','') or a.get('property','')).lower()=='citation_pdf_url':
            self.urls.append(a.get('content',''))

def cloud_sources(r,attempts):
    if not r['pmcid']: return []
    raw,_=get(CLOUD+'?'+urlencode({'list-type':'2','prefix':'metadata/'+r['pmcid']+'.','max-keys':'100'}),2000000)
    root=ET.fromstring(raw)
    keys=[n.text for n in root.iter() if n.tag.endswith('}Key') and n.text and n.text.endswith('.json')]
    sources=[]
    for key in keys:
        raw,_=get(CLOUD+key,2000000); meta=json.loads(raw)
        (OUT/'source_metadata'/('%02d_'%r['n']+Path(key).name)).write_bytes(raw)
        if norm(meta.get('doi'))!=norm(r['doi']) and str(meta.get('pmid'))!=r['pmid']: continue
        if str(meta.get('is_retracted','')).lower() in ('yes','true','1'):
            attempts.append({'source':key,'error':'Retracted; not delivered as ordinary article'}); continue
        if meta.get('pdf_url'):
            manuscript=str(meta.get('is_manuscript','')).lower() in ('yes','true','1')
            sources.append({'url':meta['pdf_url'],'version':'accepted_manuscript' if manuscript else 'published_PMC','license':meta.get('license_code',''),'metadata_url':CLOUD+key,'identity':'PMC DOI/PMID'})
    return sorted(sources,key=lambda s:s['version']=='accepted_manuscript')

def check_save(r,s):
    data,final=get(s['url'])
    if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-16384:]:
        raise ValueError('Not a complete PDF; HTML/login/errors rejected')
    md5=parse_qs(urlparse(s['url']).query).get('md5',[])
    if md5 and hashlib.md5(data).hexdigest()!=md5[0]: raise ValueError('MD5 mismatch')
    reader=PdfReader(io.BytesIO(data),strict=False)
    if reader.is_encrypted: raise ValueError('Encrypted source PDF')
    pages=len(reader.pages)
    text='\n'.join(reader.pages[i].extract_text() or '' for i in range(min(3,pages)))
    nt=norm(text); title=norm(r['title'])
    doi_match=norm(r['doi']) in nt
    title_match=len(title)>28 and title in nt
    if not (doi_match or title_match): raise ValueError('Target DOI/title absent from first three pages')
    if pages<1: raise ValueError('Empty PDF')
    name=re.sub('[^A-Za-z0-9._-]+','_',unicodedata.normalize('NFKD',r['title']).encode('ascii','ignore').decode())[:95].strip('_')
    path='PDFs/%02d_%s__%s.pdf'%(r['n'],name,s.get('version','public_version_check'))
    (OUT/path).write_bytes(data)
    return {**r,'status':'downloaded','file':path,'source_url':s['url'],'resolved_url':final,'version':s.get('version','public_version_check'),'license':s.get('license','not_separately_verified'),'metadata_url':s.get('metadata_url',''),'pages':pages,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'doi_match':doi_match,'title_match':title_match}

def openalex_sources(r,attempts):
    url='https://api.openalex.org/works/https://doi.org/'+quote(r['doi'],safe='/')
    raw,_=get(url,8000000); meta=json.loads(raw)
    (OUT/'source_metadata'/('%02d_openalex.json'%r['n'])).write_bytes(raw)
    if norm(meta.get('doi',''))!=norm('https://doi.org/'+r['doi']): return []
    out=[]
    for loc in meta.get('locations',[]):
        if not loc.get('is_oa'): continue
        version=loc.get('version') or 'public_version_check'
        if version=='submittedVersion': continue
        if loc.get('pdf_url'):
            out.append({'url':loc['pdf_url'],'version':version,'license':loc.get('license') or 'unspecified','metadata_url':url})
        elif loc.get('landing_page_url') and 'ncbi.nlm.nih.gov' not in loc['landing_page_url']:
            out.append({'landing':loc['landing_page_url'],'version':version,'license':loc.get('license') or 'unspecified','metadata_url':url})
    return out

def landing_sources(r,landing,version='publisher_metadata',license='not_separately_verified'):
    if any(x in landing for x in ('pmc.ncbi.nlm.nih.gov','ncbi.nlm.nih.gov/pmc','iris.unito.it')): return []
    raw,final=get(landing,8000000)
    if raw.startswith(b'%PDF-'): return [{'url':final,'version':version,'license':license}]
    html=raw.decode('utf-8','replace')
    if norm(r['doi']) not in norm(unquote(html)): return []
    parser=Metadata(); parser.feed(html)
    return [{'url':urljoin(final,u),'version':version,'license':license,'metadata_url':final} for u in parser.urls if u]

def retrieve(r):
    attempts=[]; seen=set()
    def try_sources(sources):
        for s in sources:
            url=s.get('url','')
            if not url or url in seen: continue
            seen.add(url)
            try:
                result=check_save(r,s); result['attempts']=attempts
                print('SAVED %02d %d pages %d bytes %s'%(r['n'],result['pages'],result['bytes'],result['version']),flush=True)
                return result
            except Exception as e:
                attempts.append({'url':url,'error':str(e)[:250]})
        return None
    if r['pmcid']:
        try:
            result=try_sources(cloud_sources(r,attempts))
            if result:return result
        except Exception as e: attempts.append({'stage':'PMC_cloud','error':str(e)[:250]})
    sources=[{'url':u,'version':'publisher_online_first' if r['n']==16 else 'publisher_PDF'} for u in DIRECT.get(r['n'],[])]
    result=try_sources(sources)
    if result:return result
    try:
        candidates=openalex_sources(r,attempts)
        result=try_sources([s for s in candidates if 'url' in s])
        if result:return result
        for s in candidates:
            if 'landing' not in s:continue
            try:
                result=try_sources(landing_sources(r,s['landing'],s['version'],s['license']))
                if result:return result
            except Exception as e:attempts.append({'url':s['landing'],'error':str(e)[:200]})
    except Exception as e: attempts.append({'stage':'OpenAlex','error':str(e)[:250]})
    if not r['pmcid']:
        try:
            url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':'DOI:"'+r['doi']+'"','format':'json','resultType':'core','pageSize':5})
            raw,_=get(url,4000000); meta=json.loads(raw)
            (OUT/'source_metadata'/('%02d_europepmc.json'%r['n'])).write_bytes(raw)
            for m in meta.get('resultList',{}).get('result',[]):
                if norm(m.get('doi',''))==norm(r['doi']) and m.get('pmcid'):
                    r['pmcid']=m['pmcid']; result=try_sources(cloud_sources(r,attempts))
                    if result:return result
        except Exception as e:attempts.append({'stage':'EuropePMC','error':str(e)[:250]})
    try:
        result=try_sources(landing_sources(r,'https://doi.org/'+r['doi']))
        if result:return result
    except Exception as e:attempts.append({'stage':'publisher','error':str(e)[:250]})
    print('MISSING %02d %s'%(r['n'],r['doi']),flush=True)
    return {**r,'status':'not_downloaded','attempts':attempts}

def main():
    records=[]
    for line in DATA.splitlines():
        n,doi,pmid,pmcid,title=line.split('|',4)
        records.append({'n':int(n),'doi':doi,'pmid':pmid,'pmcid':pmcid,'title':title})
    results=[]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(retrieve,r):r for r in records}
        for f in cf.as_completed(futures):
            try:results.append(f.result())
            except Exception as e: results.append({**futures[f],'status':'error','error':str(e)})
            (OUT/'results.json').write_text(json.dumps(sorted(results,key=lambda r:r['n']),ensure_ascii=False,indent=2),encoding='utf-8')
    results.sort(key=lambda r:r['n'])
    count=sum(r['status']=='downloaded' for r in results)
    summary={'requested':len(records),'downloaded':count,'missing':[r['n'] for r in results if r['status']!='downloaded'],'downloaded_numbers':[r['n'] for r in results if r['status']=='downloaded'],'total_pdf_bytes':sum(r.get('bytes',0) for r in results)}
    (OUT/'README.txt').write_text('Original public-source PDF files, not regenerated documents.\nSource: publishers, institutional repositories and NLM PMC Article Datasets.\nSnapshot retrieved 2026-09-18. No claim of latest versions after this date.\nNLM/NIH/HHS does not endorse this collection. Retain and observe each article license.\nThe results.json file records actual successes and failures, source URLs, versions, PDF identity checks, and SHA-256 hashes.\nNo paywall, CAPTCHA or authentication bypass was used.\n',encoding='utf-8')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in OUT.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(OUT)))
    key=AESGCM.generate_key(bit_length=256); nonce=os.urandom(12)
    cipher=AESGCM(key).encrypt(nonce,stream.getvalue(),b'CRC50-20260918')
    public=serialization.load_pem_public_key(PUBLIC_KEY)
    wrapped=public.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    artifact=Path('encrypted_artifact'); artifact.mkdir(exist_ok=True)
    (artifact/'bundle.aesgcm').write_bytes(nonce+cipher)
    (artifact/'bundle.key').write_bytes(wrapped)
    (artifact/'summary.json').write_text(json.dumps(summary,indent=2))
    print('FINAL_SUMMARY '+json.dumps(summary),flush=True)
    print('ENCRYPTED_ARTIFACT_READY',flush=True)

if __name__=='__main__':main()
