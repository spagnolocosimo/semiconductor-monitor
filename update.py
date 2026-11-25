"""Market data and SEC 13F refresh; safe fallbacks and explicit provenance."""
import json, os, re, time, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
ROOT=Path(__file__).parent
WATCH=['SMH','SOXX','MU','NVDA','TSM','ASML','AMAT','LRCX']
CUSIPS={'MU':'595112103','NVDA':'67066G104','TSM':'874039100','ASML':'N07059210','AMAT':'038222105','LRCX':'512807306'}
now=datetime.now(ZoneInfo('Europe/Amsterdam'))
if os.environ.get('SCHEDULE_EVENT')=='schedule' and (now.weekday()>4 or now.hour!=22):raise SystemExit('Wrong Amsterdam slot')
def get(url):
    email = os.environ.get("SEC_CONTACT_EMAIL")

    if not email:
        raise RuntimeError("SEC_CONTACT_EMAIL is not configured")

    req = Request(
        url,
        headers={
            "User-Agent": f"Cosimo Spagnolo SemiconductorMonitor {email}",
            "Accept-Encoding": "identity"
        }
    )

    with urlopen(req, timeout=16) as r:
        return r.read()
def readjson(path,default):
 try:return json.loads(path.read_text())
 except Exception:return default
cur=readjson(ROOT/'data/curated.json',{})
old=readjson(ROOT/'data/latest.json',{})
prices=old.get('assets',[]);price_asof=old.get('price_as_of','Not available');price_fresh=False
try:
 import yfinance as yf
 df=yf.download(WATCH,period='7mo',interval='1d',auto_adjust=False,progress=False,threads=False)
 import pandas as pd
 today_ny=datetime.now(ZoneInfo('America/New_York')).date()
 new=[];dates=[]
 for t in WATCH:
  try:
   x=df['Close'][t].dropna();x=x[[i.date()<today_ny for i in x.index]]
   wk=x.resample('W-FRI').last().dropna();v=list(map(float,wk.values));last=x.index[-1].date().isoformat();dates.append(last)
   four=v[-4:] if len(v)>=4 else []
   ret=four[-1]/four[0]-1 if len(four)==4 else None
   status='RED' if ret is not None and ret<-.05 else 'YELLOW' if ret is not None else 'UNKNOWN'
   new.append({'ticker':t,'last_close':round(v[-1],2),'four_closes':[round(z,2) for z in four],'three_week_return':round(ret,5) if ret is not None else None,'signal':status,'as_of':last,'history':v[-15:]})
  except Exception as exc:print('Price missing',t,exc)
 if len(new)>=6:prices=new;price_asof=min(dates);price_fresh=True
except Exception as exc:print('Price feed unavailable',exc)
# SEC filings: retrieve recent 13F submission metadata, then parse both information-table XMLs.
# Fail closed: only replace a manager's rows when BOTH quarter tables were parsed.
def tag(x):return x.tag.split('}')[-1].lower()
def children(node,name):return [c for c in node.iter() if tag(c)==name.lower()]
def parse_table(raw):
 root=ET.fromstring(raw); entries=children(root,'infoTable'); result={}
 for entry in entries:
  def field(n):
   found=children(entry,n);return (found[0].text or '').strip() if found else ''
  cusip=field('cusip').upper(); putcall=field('putCall').upper()
  if cusip not in CUSIPS.values() or putcall:continue
  shares=field('sshPrnamt');unit=field('sshPrnamtType').upper()
  if unit and unit!='SH':continue
  try:result[cusip]=result.get(cusip,0)+int(float(shares.replace(',','')))
  except ValueError:pass
 if not entries:raise ValueError('No infoTable entries')
 return result

def filing(cik,period):
 url=f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json';data=json.loads(get(url));r=data['filings']['recent']
 matches=[]
 for i,(form,p) in enumerate(zip(r['form'],r['reportDate'])):
  if form in ('13F-HR','13F-HR/A') and p==period:matches.append((r['filingDate'][i],r['accessionNumber'][i]))
 if not matches:return None
 _,acc=sorted(matches)[-1];base=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace("-", "")}/'
 idx=json.loads(get(base+'index.json'));items=idx['directory']['item']
 # Inspect XML roots, not guessed filenames. Avoid primary_doc.xml and submission metadata.
 candidates=[z['name'] for z in items if z['name'].lower().endswith('.xml') and not z['name'].lower().startswith(('primary_doc','filing'))]
 for name in candidates:
  try:
   raw=get(base+name)
   if b'infoTable' in raw or b'infotable' in raw:
    return parse_table(raw),base+name
  except Exception:continue
 return None

existing=cur.get('filings',[])
filings=list(existing);errors=[];updated_managers=[]
if os.environ.get('SKIP_SEC')!='1':
 for m in readjson(ROOT/'managers.json',[]):
  try:
   q2=filing(m['cik'],'2026-06-30');q3=filing(m['cik'],'2026-09-30')
   if not q2 or not q3:raise ValueError('One or both information tables missing')
   rows=[]
   for t,c in CUSIPS.items():
    a=q2[0].get(c,0);b=q3[0].get(c,0)
    if a or b:rows.append({'manager':m['name'],'ticker':t,'q2':a,'q3':b,'source':q3[1],'q2_source':q2[1],'period':'2026-09-30','quality':'SEC XML Q2 and Q3 parsed; common shares only'})
   filings=[x for x in filings if x['manager']!=m['name']]+rows
   updated_managers.append(m['name']);print('SEC',m['name'],len(rows))
  except Exception as exc:errors.append(f'{m["name"]}: {str(exc)[:95]}');print('SEC unavailable',errors[-1])
  time.sleep(.2)
# Save successful SEC rows to curated for resilience, but never replace on failure.
if updated_managers:
 cur['filings']=filings;(ROOT/'data/curated.json').write_text(json.dumps(cur,indent=2)+'\n')
# ETF flows are *daily observations*, not full-week sums. Never count as weekly inflow confirmation.
flows=sorted(cur.get('flows',[]),key=lambda x:x['date'],reverse=True)
trades=sorted(cur.get('trades',[]),key=lambda x:x['date'],reverse=True)
# No positive institutional-reentry verdict without full-week flow + 2 independent manager confirmations.
red=sum(a.get('signal')=='RED' for a in prices if a.get('ticker') in ('SMH','SOXX'))
signal='RED' if price_fresh and red else 'YELLOW' if price_fresh else 'UNKNOWN'
out={'generated_at_amsterdam':now.strftime('%Y-%m-%d %H:%M %Z'),'price_as_of':price_asof,'price_fresh':price_fresh,'signal':signal,'headline':'Recovery NOT confirmed' if price_fresh else 'Fresh prices unavailable','reason':'Dated flows are partial, institutional daily transactions cover ARK only; quarterly 13Fs are lagged. GREEN is deliberately withheld until independent confirmation.','assets':prices,'flows':flows,'trades':trades,'filings':sorted(filings,key=lambda x:(x['manager'],x['ticker'])),'sec_managers_updated':updated_managers,'sec_errors':errors,'source_note':'Market prices Yahoo Finance; flows ETF.com; dated ARK events third-party; SEC holdings directly parsed when available.'}
(ROOT/'data/latest.json').write_text(json.dumps(out,indent=2)+'\n')
print('Complete',len(filings),'SEC holdings',len(flows),'flow events',len(trades),'trades')
