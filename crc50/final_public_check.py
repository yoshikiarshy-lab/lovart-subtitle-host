import download as d
TARGET={24:'S0304383524003793',35:'S0304419X25001817'}
d.DATA='\n'.join(s for s in d.DATA.splitlines() if int(s.split('|',1)[0]) in TARGET)
def retrieve(r):
 attempts=[]
 urls=['https://api.elsevier.com/content/article/doi/'+r['doi']+'?httpAccept=application/pdf','https://www.sciencedirect.com/science/article/pii/'+TARGET[r['n']]+'/pdfft?isDTMRedir=true&download=true']
 for url in urls:
  try:
   v=d.check_save(r,{'url':url,'version':'publisher_PDF','license':'cc-by'});v['attempts']=attempts;return v
  except Exception as e:attempts.append({'url':url,'error':str(e)[:250]})
 return {**r,'status':'not_downloaded','attempts':attempts}
d.retrieve=retrieve
d.main()
