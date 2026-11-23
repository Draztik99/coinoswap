"""Fail-closed CoinoSwap price/image preparation. NEVER publishes to social media."""
import os,sys,json,math,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import requests
from render_rates import render
from posting_slots import slot_for_date, expected_prepare_time

SAST=ZoneInfo('Africa/Johannesburg')
COINS={'BTC':(1,'XBTUSD',1.0),'ETH':(1027,'ETHUSD',1.0),'XMR':(328,'XMRUSD',2.0)}
SESSION=requests.Session()
SESSION.headers.update({'User-Agent':'CoinoSwap-Daily-Rates/1.0'})

class Block(Exception): pass

def checked(symbol,source,price,timestamp,unix=False):
    try:
        value=float(price)
        stamp=(datetime.fromtimestamp(float(timestamp),timezone.utc) if unix
            else datetime.fromisoformat(str(timestamp).replace('Z','+00:00')))
        if stamp.tzinfo is None: raise ValueError('timezone missing')
        age=(datetime.now(timezone.utc)-stamp).total_seconds()
        if not (math.isfinite(value) and value>0 and -30<=age<=300):
            raise ValueError('bad price or timestamp age')
    except (TypeError,ValueError,OverflowError):
        raise Block(source+' '+symbol+' missing/invalid/stale price or timestamp')
    return {'usd':value,'updated_sast':stamp.astimezone(SAST).isoformat(timespec='seconds'),
            'age_seconds':round(age,1)}

def cmc(key):
    try:
        r=SESSION.get('https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest',
            params={'id':'1,1027,328','convert':'USD'},
            headers={'X-CMC_PRO_API_KEY':key},timeout=20)
        r.raise_for_status()
        j=r.json()
    except (requests.RequestException,ValueError): raise Block('CoinMarketCap unavailable')
    # CoinMarketCap V3 returns "0" as a string on successful responses.
    status=j.get('status') or {}
    try:
        error_code=int(status.get('error_code'))
    except (ValueError,TypeError):
        raise Block('CoinMarketCap missing/invalid API status code')
    if error_code != 0: raise Block(f'CoinMarketCap API error code {error_code}')
    rows=j.get('data')
    if isinstance(rows,dict): rows=list(rows.values())
    if not isinstance(rows,list): raise Block('CoinMarketCap missing records')
    out={}
    for sym,(asset_id,_,_) in COINS.items():
        exact=[v for v in rows if isinstance(v,dict) and v.get('id')==asset_id and v.get('symbol')==sym]
        if len(exact)!=1: raise Block('CMC wrong asset ID/symbol for '+sym)
        quotes=exact[0].get('quote')
        if isinstance(quotes,dict): usd=quotes.get('USD')
        elif isinstance(quotes,list):
            found=[v for v in quotes if isinstance(v,dict) and (v.get('symbol')=='USD' or v.get('id')==2781)]
            usd=found[0] if len(found)==1 else None
        else: usd=None
        if not isinstance(usd,dict) or not usd.get('last_updated'):
            raise Block('CMC missing USD quote '+sym)
        out[sym]=checked(sym,'CMC',usd.get('price'),usd['last_updated'])
    return out

def kraken():
    out={}
    for sym,(_,pair,_) in COINS.items():
        try:
            r=SESSION.get('https://api.kraken.com/0/public/Trades',
                          params={'pair':pair,'count':10},timeout=20)
            r.raise_for_status()
            j=r.json()
        except (requests.RequestException,ValueError): raise Block('Kraken unavailable '+sym)
        if j.get('error') or not isinstance(j.get('result'),dict): raise Block('Kraken API error '+sym)
        values=[v for k,v in j['result'].items() if k!='last']
        if len(values)!=1 or not isinstance(values[0],list): raise Block('No Kraken trades '+sym)
        trades=[v for v in values[0] if isinstance(v,list) and len(v)>=3]
        if not trades: raise Block('Bad Kraken trades '+sym)
        last=max(trades,key=lambda v:float(v[2]))
        out[sym]=checked(sym,'Kraken',last[0],last[2],unix=True)
    return out

def main():
    now=datetime.now(SAST)
    emergency=os.environ.get('EMERGENCY_RATES','').lower()=='true'
    target_hour,target_minute=slot_for_date(now.date())
    prepare_hour,prepare_minute=expected_prepare_time(now.date())
    if emergency:
        # Manual recovery only. Target is 3 minutes after fresh quote retrieval begins.
        recovery_target=(now+timedelta(minutes=3)).replace(second=0,microsecond=0)
        if recovery_target.date()!=now.date(): raise Block('Emergency crosses SAST date')
        target_hour,target_minute=recovery_target.hour,recovery_target.minute
    if not emergency and not (prepare_hour*60+prepare_minute <= now.hour*60+now.minute < target_hour*60+target_minute-1):
        raise Block(f'Outside selected fresh-quote window {prepare_hour:02}:{prepare_minute:02} until one minute before target SAST for {target_hour:02}:{target_minute:02} post')
    key=os.environ.get('CMC_API_KEY','').strip()
    if not key: raise Block('CMC_API_KEY Actions secret missing')
    primary=cmc(key)
    secondary=kraken()
    audits={}
    display={}
    for sym,(_,_,limit) in COINS.items():
        a,b=primary[sym],secondary[sym]
        delta=100*abs(a['usd']-b['usd'])/a['usd']
        if delta>limit: raise Block(sym+' source deviation exceeds limit')
        display[sym]=a['usd']
        audits[sym]={'display_usd':round(a['usd'],2),'coinmarketcap':a,
                     'kraken':b,'deviation_pct':round(delta,5),'threshold_pct':limit}
    # Prices must be fresh at the selected publication slot, not only at retrieval.
    target=now.replace(hour=target_hour,minute=target_minute,second=0,microsecond=0)
    for sym in COINS:
        for source_name,item in [('CoinMarketCap',primary[sym]),('Kraken',secondary[sym])]:
            updated=datetime.fromisoformat(item['updated_sast'])
            remaining=(target-updated).total_seconds()
            if not 0<=remaining<=300:
                raise Block(f'{sym} {source_name} data outside five-minute freshness range at {target_hour:02}:{target_minute:02}')
    date=now.date().isoformat()
    out=Path('docs/daily-rates')
    out.mkdir(parents=True,exist_ok=True)
    img=out/(date+'.png')
    audit=out/(date+'.json')
    if img.exists() or audit.exists(): raise Block('Duplicate daily asset')
    prior=out/((now.date()-timedelta(days=1)).isoformat()+'.json')
    if prior.exists():
        old=json.loads(prior.read_text(encoding='utf-8'))
        for sym in COINS:
            value=float(old['coins'][sym]['display_usd'])
            if value<=0 or abs(display[sym]-value)/value>.25:
                raise Block(sym+' price change over 25% vs previous day')
    temp=out/('.'+date+'.temp.png')
    try:
        strings=render(display,now,temp)
        completed=datetime.now(SAST)
        if completed.date()!=now.date() or completed >= target-timedelta(minutes=1):
            raise Block('Image completed after preparation cutoff')
        image_hash=hashlib.sha256(temp.read_bytes()).hexdigest()
        text=(f"Your {now.day} {now.strftime('%B')} crypto price check 📊\n"
              "$BTC, $ETH and $XMR.\n\nNo need to jump between exchanges.\n"
              "Compare offers and swap in one place.\n\nNo account needed.\n\n"
              "👉 coinoswap.com\n\n")
        record={'status':'VALIDATED','approval_state':'NOT_PUBLISHED',
                'date_sast':date,'checked_at_sast':completed.isoformat(timespec='seconds'),
                'target_sast':target.isoformat(timespec='seconds'),'coins':audits,
                'experiment':{'slot_sast':f'{target_hour:02}:{target_minute:02}','week_start_sast':(now.date()-timedelta(days=now.weekday())).isoformat()},
                'image':{'filename':img.name,'sha256':image_hash,'width':1536,'height':1024},
                'display_prices':strings,'caption':text}
        temp.rename(img)
        audit.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print('VALIDATED assets:',img,audit)
    finally:
        temp.unlink(missing_ok=True)

if __name__=='__main__':
    try: main()
    except (Block,ValueError,KeyError,FileNotFoundError) as error:
        print('FAIL CLOSED — DO NOT PUBLISH:',error,file=sys.stderr)
        sys.exit(2)
