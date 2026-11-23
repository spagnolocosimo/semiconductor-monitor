"""Refresh public price observations. Dated flow/trade evidence is curated, never guessed."""
import json,os
from datetime import datetime,timedelta,time
from pathlib import Path
from zoneinfo import ZoneInfo
from collections import defaultdict
ROOT=Path(__file__).parent
NOW=datetime.now(ZoneInfo('Europe/Amsterdam'))
if os.environ.get('SCHEDULE_EVENT')=='schedule' and (NOW.weekday()>4 or NOW.hour!=22):
 print('Not the Amsterdam 22:00 slot; skipping.');raise SystemExit(0)
WATCH={'SMH':'Market ETF','SOXX':'Market ETF','MU':'HBM / memory','NVDA':'AI accelerators','TSM':'Foundry','ASML':'Lithography','AMAT':'Equipment','LRCX':'Equipment'}
# No stale snapshot is ever relabeled as today's prices.
old_path=ROOT/'data/latest.json'
old=json.loads(old_path.read_text()) if old_path.exists() else {}
assets=[];maxdate=None;histories={}
try:
 import yfinance as yf
 import pandas as pd
 # One download, auto_adjust=False to keep close prices in reported USD units.
 result=yf.download(list(WATCH),period='7mo',interval='1d',auto_adjust=False,progress=False,threads=False)
 for ticker,role in WATCH.items():
  try:
   sub=result['Close'][ticker].dropna() if hasattr(result['Close'],'columns') else result['Close'].dropna()
   # At 22 Amsterdam, NYSE may be open: include only trading dates strictly earlier than today's NY date.
   ny_today=datetime.now(ZoneInfo('America/New_York')).date()
   sub=sub[[x.date()<ny_today for x in sub.index]]
   weekly=sub.resample('W-FRI').last().dropna()
   dates=[x.date().isoformat() for x in weekly.index]
   vals=[round(float(v),4) for v in weekly.values]
   histories[ticker]=dict(dates=dates,values=vals)
   if len(sub):maxdate=max(maxdate or sub.index[-1].date(),sub.index[-1].date())
  except Exception as exc:print('Ticker error',ticker,exc)
except Exception as exc:print('Price feed unavailable:',exc)
# Curated records must carry direct source, date and confidence. Never auto-create from prices.
evidence_path=ROOT/'data/curated_evidence.json'
curated=json.loads(evidence_path.read_text()) if evidence_path.exists() else {'flows':[],'trades':[],'filings':[]}
flows=[x for x in curated.get('flows',[]) if x.get('source') and x.get('verified') is True]
trades=[x for x in curated.get('trades',[]) if x.get('source') and x.get('verified') is True]
filings=[x for x in curated.get('filings',[]) if x.get('source') and x.get('verified') is True]
for ticker,role in WATCH.items():
 h=histories.get(ticker,{});v=h.get('values',[]);dates=h.get('dates',[])
 recent=(maxdate is not None and dates and (maxdate-datetime.fromisoformat(dates[-1]).date()).days<=7)
 four=v[-4:] if len(v)>=4 and recent else []
 ret=four[-1]/four[0]-1 if len(four)==4 else None
 if ret is None:signal='UNKNOWN'
 elif ret<-.05:signal='RED'
 elif ret<=.02:signal='YELLOW'
 else:signal='YELLOW' # Price recovery alone cannot make institutional GREEN.
 assets.append(dict(ticker=ticker,role=role,last_close=round(v[-1],2) if recent else None,four_closes=[round(x,2) for x in four] if len(four)==4 else [None]*4,three_week_return=round(ret,5) if ret is not None else None,signal=signal,note='Price trend only; flow and fund trade confirmation separate.'))
# 3-week completed window: weekly ETF flows for BOTH benchmarks must be verified.
benchmark=['SMH','SOXX'];price_ok=True
for t in benchmark:
 h=histories.get(t,{});v=h.get('values',[])
 if len(v)<14 or not maxdate:price_ok=False;continue
 # last 3 weeks each above trailing 4-week mean and no new 13-week lows
 for j in range(-3,0):
  ix=len(v)+j
  if v[ix] <= sum(v[ix-3:ix+1])/4 or v[ix]<=min(v[ix-12:ix]):price_ok=False
recent_flow=[f for f in flows if f.get('ticker') in benchmark and f.get('window_end') and maxdate and 0<=(maxdate-datetime.fromisoformat(f['window_end']).date()).days<=21 and f.get('window_type')=='full_week']
positive_weeks={f['window_end'] for f in recent_flow if f.get('net_usd_m',0)>0}
flow_ok=len(positive_weeks)>=2 and {x['ticker'] for x in recent_flow}==set(benchmark)
recent_trades=[t for t in trades if t.get('date') and maxdate and 0<=(maxdate-datetime.fromisoformat(t['date']).date()).days<=21 and t.get('ticker') in WATCH and t.get('action')=='BUY' and t.get('net_buying_verified') is True]
trade_ok=len({t['manager'] for t in recent_trades})>=2
if maxdate is None:overall='UNKNOWN'
elif price_ok and flow_ok and trade_ok:overall='GREEN'
elif any(a['signal']=='RED' for a in assets[:2]):overall='RED'
else:overall='YELLOW'
headline={'GREEN':'Recovery criteria met','YELLOW':'Potential stabilization; buying not confirmed','RED':'Semiconductor recovery not confirmed','UNKNOWN':'Insufficient fresh market data'}[overall]
gates=[dict(name='Both ETF price trends',status='GREEN' if price_ok else 'RED' if any(a['signal']=='RED' for a in assets[:2]) else 'YELLOW',detail='3 weeks above 4-week mean, no new 13-week lows'),dict(name='Verified weekly ETF flows',status='GREEN' if flow_ok else 'YELLOW',detail=f'{len(positive_weeks)} positive documented week(s); need 2'),dict(name='Dated large-investor net buying',status='GREEN' if trade_ok else 'YELLOW',detail=f'{len(set(t["manager"] for t in recent_trades))} distinct confirmed manager(s); need 2')]
out={'generated_at_amsterdam':NOW.strftime('%Y-%m-%d %H:%M %Z'),'price_as_of':maxdate.isoformat() if maxdate else old.get('price_as_of'),'signal':overall,'headline':headline,'reason':'Price signals are updated automatically. Institutional flows/trades remain unconfirmed unless dated primary-source evidence has been added.','gates':gates,'assets':assets,'flows':flows,'trades':trades,'filings':filings,'data_note':'Price feed Yahoo Finance (yfinance); do not assume exchange-verified or intraday completion.'}
if maxdate is None and old.get('assets'):
 # Retain old observations but show stale status, never turn unavailable feed into false fresh prices.
 out['assets']=old['assets'];out['signal']='UNKNOWN';out['headline']='Price feed unavailable; showing last saved snapshot';out['reason']='No fresh market observations retrieved. Previously saved prices are historical only.'
old_path.write_text(json.dumps(out,indent=2)+'\n');print('Updated',out['signal'],out['price_as_of'])
