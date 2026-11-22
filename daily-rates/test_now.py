"""Sunday live API + image test. Deliberately incapable of social publishing."""
import os,sys,json,hashlib
from datetime import datetime, timezone
from pathlib import Path
from prepare_rates import SAST,COINS,cmc,kraken,Block
from render_rates import render

def main():
    key=os.environ.get("CMC_API_KEY","").strip()
    if not key: raise Block("Missing repository CMC_API_KEY secret")
    cmc_quotes=cmc(key)
    kraken_quotes=kraken()
    start=datetime.now(SAST)
    prices={}
    checks={}
    for sym,(_,_,limit) in COINS.items():
        a=cmc_quotes[sym]
        b=kraken_quotes[sym]
        deviation=100*abs(a['usd']-b['usd'])/a['usd']
        if deviation > limit:
            raise Block(f"{sym} discrepancy {deviation:.4f}% > {limit}%")
        prices[sym]=a['usd']
        checks[sym]={'display_usd':round(a['usd'],2),'coinmarketcap':a,
                     'kraken':b,'deviation_pct':round(deviation,5),
                     'threshold_pct':limit}
    folder=Path('docs/daily-rates/tests')
    folder.mkdir(parents=True,exist_ok=True)
    tag=start.strftime('%Y-%m-%dT%H%M%S')
    image=folder/(tag+'.png')
    audit=folder/(tag+'.json')
    if image.exists() or audit.exists():
        raise Block('Duplicate test image')
    render_prices=render(prices,start,image)
    checked_at=datetime.now(SAST)
    for sym in COINS:
        for key_name in ['coinmarketcap','kraken']:
            tick=datetime.fromisoformat(checks[sym][key_name]['updated_sast'])
            age=(checked_at-tick).total_seconds()
            if not 0 <= age <= 300:
                image.unlink(missing_ok=True)
                raise Block(f"{sym} {key_name} stale at rendering ({age:.0f} secs)")
    sha=hashlib.sha256(image.read_bytes()).hexdigest()
    caption=(f"Your {start.day} {start.strftime('%B')} crypto price check 📊\n"
        "$BTC, $ETH and $XMR.\n\n"
        "No need to jump between exchanges.\n"
        "Compare offers and swap in one place.\n"
        "No account needed.\n\n👉 coinoswap.com\n\n")
    result={
       'status':'TEST_ONLY_DO_NOT_PUBLISH',
       'published':False,
       'date_sast':start.date().isoformat(),
       'checked_at_sast':checked_at.isoformat(timespec='seconds'),
       'prices':checks,
       'display_prices':render_prices,
       'image':{'filename':image.name,'sha256':sha,'width':1536,'height':1024},
       'caption':caption,
       'warning':'Review preview only. Prices must be REFRESHED AND REVALIDATED before publishing. This workflow does not publish.'
    }
    audit.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('SUCCESS — PREVIEW ONLY:', image, audit)
    print('Market check time:',checked_at.isoformat())
    print('Prices:',json.dumps(render_prices))
    print('DO NOT PUBLISH THIS HISTORICAL PREVIEW WITHOUT REFRESHING ALL PRICES.')

if __name__=='__main__':
    try: main()
    except (Block,ValueError,KeyError,FileNotFoundError) as e:
        print("FAIL CLOSED — NO PREVIEW, NO PUBLISH:",e,file=sys.stderr)
        sys.exit(2)
