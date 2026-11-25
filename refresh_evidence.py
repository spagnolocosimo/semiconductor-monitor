"""Conservative ETF.com daily-flow importer. Only clearly dated, sourced ticker rows."""
import json,re,urllib.request
from pathlib import Path
from datetime import datetime,timedelta
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parent
FILE=ROOT/'data/curated.json'
INDEX='https://www.etf.com/sections/daily-etf-flows'
UA='Mozilla/5.0 (compatible; SemiconductorCapitalMonitor/2.2; research data importer)'
def html(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA})
 with urllib.request.urlopen(req,timeout=18) as r:return r.read().decode('utf-8','replace')
def number(x):
 try:return float(x.replace(',','').replace('$','').replace('−','-').strip())
 except:return None

def extract(url):
 soup=BeautifulSoup(html(url),'html.parser');text=soup.get_text(' ',strip=True)
 # Explicit article statement "flows for November 10, 2026"; never infer from publication date.
 match=re.search(r'(?:fund flows for|flows for)\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})',text,re.I)
 if not match:return []
 try:date=datetime.strptime(match.group(1),'%B %d, %Y').date().isoformat()
 except ValueError:return []
 found=[]
 for table in soup.find_all('table'):
  for tr in table.find_all('tr'):
   cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'],recursive=False)]
   if not cells:continue
   tick=next((c.strip() for c in cells[:2] if c.strip() in ('SMH','SOXX')),None)
   if not tick:continue
   # Use flow value only if the table has a "Net Flows" header; never confuse AUM with flows.
   headings=[c.get_text(' ',strip=True).lower() for c in table.find_all('th')]
   flowcol=next((i for i,h in enumerate(headings) if 'net flow' in h),None)
   if flowcol is None or flowcol>=len(cells):continue
   value=number(cells[flowcol])
   if value is None:continue
   found.append(dict(date=date,ticker=tick,usd_m=value,source=url,quality='ETF.com dated daily creations/redemptions; automated table extraction; review source if revised'))
 return found

def main():
 data=json.loads(FILE.read_text());existing={(x['date'],x['ticker']):x for x in data.get('flows',[])}
 try:
  soup=BeautifulSoup(html(INDEX),'html.parser');urls=[]
  for a in soup.select('a[href]'):
   href=a.get('href','')
   if '/sections/daily-etf-flows/' not in href or href.endswith('/archive'):continue
   url=href if href.startswith('https://') else 'https://www.etf.com'+href
   if url not in urls:urls.append(url)
  for url in urls[:18]:
   try:
    for row in extract(url):existing[(row['date'],row['ticker'])]=row
   except Exception as exc:print('Article unavailable',url,str(exc)[:90])
 except Exception as exc:print('ETF.com unavailable; retained previous observations',str(exc)[:120])
 data['flows']=sorted(existing.values(),key=lambda x:x['date'],reverse=True)
 FILE.write_text(json.dumps(data,indent=2)+'\n')
 print('ETF flow observations',len(data['flows']))
if __name__=='__main__':main()
