#!/usr/bin/env python3
"""Normal browser retrieval: no stealth, no CAPTCHA solver, no credentials."""
import asyncio,json,hashlib,io,re,time
from pathlib import Path
from urllib.parse import urljoin
import deep_retrieval as base
import download as d
from pypdf import PdfReader
from playwright.async_api import async_playwright

OUT=Path('browser_result');OUT.mkdir(exist_ok=True)
for x in ['PDFs','pages','assets']:(OUT/x).mkdir(exist_ok=True)
base.OUT=OUT
RECS={r['n']:r for r in base.RECORDS}
TARGETS={
1:['https://pmc.ncbi.nlm.nih.gov/articles/PMC10365888/','https://pmc.ncbi.nlm.nih.gov/articles/PMC10365888/pdf/nihms-1915339.pdf'],
6:['https://pmc.ncbi.nlm.nih.gov/articles/PMC9924026/','https://pmc.ncbi.nlm.nih.gov/articles/PMC9924026/pdf/nihms-1864616.pdf'],
34:['https://pmc.ncbi.nlm.nih.gov/articles/PMC8968072/','https://pmc.ncbi.nlm.nih.gov/articles/PMC8968072/pdf/nihms-1787436.pdf'],
8:['https://onlinelibrary.wiley.com/doi/full/10.1002/jso.27320','https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/jso.27320'],
24:['https://www.sciencedirect.com/science/article/pii/S0304383524003793','https://publications.goettingen-research-online.de/handle/2/144096'],
35:['https://www.sciencedirect.com/science/article/pii/S0304419X25001817'],
36:['https://www.sciencedirect.com/science/article/abs/pii/S2210740122001176'],
37:['https://onlinelibrary.wiley.com/doi/full/10.1002/jso.27848','https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/jso.27848'],
42:['https://onlinelibrary.wiley.com/doi/full/10.1002/ijc.35425','https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/ijc.35425'],
44:['https://www.researchgate.net/publication/353369863_Postoperative_complications_of_colorectal_cancer'],
50:['https://doi.org/10.1159/000540594','https://karger.com/dig/article-pdf/106/2/122/4271927/000540594.pdf']}
RESULTS=[]

def save(n,data,url,version='source_version_to_verify'):
    if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-16384:]:return None
    reader=PdfReader(io.BytesIO(data),strict=False)
    if reader.is_encrypted:return None
    text='\n'.join(p.extract_text() or '' for p in reader.pages[:3]);r=RECS[n]
    if d.norm(r['doi']) not in d.norm(text) and d.norm(r['title']) not in d.norm(text):return None
    path='PDFs/%02d_original.pdf'%n;(OUT/path).write_bytes(data)
    return dict(n=n,file=path,source_url=url,version=version,pages=len(reader.pages),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),doi=r['doi'],title=r['title'])

async def work(browser,n,urls,sem):
    async with sem:
        ctx=await browser.new_context(accept_downloads=True)
        page=await ctx.new_page();page.set_default_timeout(18000)
        logs=[];good=[];downloads=[]
        async def on_download(dl):
            try:
                p=await dl.path()
                if p:
                    r=save(n,Path(p).read_bytes(),dl.url)
                    if r:good.append(r)
            except Exception as e:logs.append(dict(download_error=str(e)[:200]))
        async def on_response(resp):
            try:
                if 'application/pdf' in resp.headers.get('content-type',''):
                    r=save(n,await resp.body(),resp.url)
                    if r:good.append(r)
            except Exception:pass
        page.on('download',lambda dl:downloads.append(asyncio.create_task(on_download(dl))))
        page.on('response',lambda r:asyncio.create_task(on_response(r)))
        for u in urls:
            if good:break
            try:
                await page.goto(u,wait_until='domcontentloaded',timeout=35000)
                await page.wait_for_timeout(7000)
            except Exception as e:logs.append(dict(url=u,navigation=str(e)[:250]))
            if good:break
            try:
                html=await page.content();txt=await page.locator('body').inner_text(timeout=5000)
                path='pages/%02d_%s.html'%(n,hashlib.sha256(u.encode()).hexdigest()[:9]);(OUT/path).write_text(html)
                entry=dict(url=u,final_url=page.url,title=await page.title(),page=path,text_length=len(txt),text_start=txt[:300])
                # Interactive challenges/authentication are not solved or bypassed.
                if any(s in txt[:1200].lower() for s in ['verify you are human','captcha','access denied','checking your browser','just a moment','robot']):
                    entry['status']='access_challenge_not_bypassed';logs.append(entry);continue
                links=await page.locator('a[href]').evaluate_all('(as)=>as.map(a=>({href:a.href,text:a.innerText}))')
                pdfs=await page.locator('meta[name="citation_pdf_url"]').evaluate_all('(ms)=>ms.map(m=>m.content)')
                for a in links:
                    if any(s in a['text'].lower() for s in ['download full-text','view open manuscript','download pdf']) or any(s in a['href'].lower() for s in ['/pdf/','.pdf','/pdfft']):pdfs.append(a['href'])
                entry['downloads']=list(dict.fromkeys(pdfs));logs.append(entry)
                for pdf in entry['downloads'][:6]:
                    try:
                        resp=await ctx.request.get(pdf,timeout=25000)
                        data=await resp.body();r=save(n,data,pdf)
                        if r:good.append(r);break
                        logs.append(dict(pdf_url=pdf,status=resp.status,bytes=len(data),not_pdf_start=data[:200].decode('utf-8','replace')))
                        if resp.ok and data.lstrip().startswith(b'<'):
                            try:await page.goto(pdf,wait_until='domcontentloaded',timeout=20000);await page.wait_for_timeout(5000)
                            except Exception:pass
                    except Exception as e:logs.append(dict(pdf_url=pdf,error=str(e)[:200]))
                    if good:break
            except Exception as e:logs.append(dict(url=u,error=str(e)[:250]))
        if downloads:await asyncio.gather(*downloads,return_exceptions=True)
        res=dict(n=n,status='downloaded' if good else 'not_downloaded',files=good[:1],attempts=logs)
        RESULTS.append(res);print('BROWSER_RESULT',n,res['status'],flush=True)
        (OUT/'results.json').write_text(json.dumps(sorted(RESULTS,key=lambda r:r['n']),ensure_ascii=False,indent=2))
        await ctx.close()

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        sem=asyncio.Semaphore(3)
        await asyncio.gather(*(work(browser,n,urls,sem) for n,urls in TARGETS.items()))
        await browser.close()
    base.pkg({'requested':len(RESULTS),'downloaded':[r['n'] for r in RESULTS if r['status']=='downloaded'],'missing':[r['n'] for r in RESULTS if r['status']!='downloaded']})

asyncio.run(main())
