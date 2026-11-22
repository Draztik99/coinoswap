"""One-off, explicitly approved LIVE media preparation. Never sends social posts."""
import os,sys,json,hashlib
from datetime import datetime,timedelta
from pathlib import Path
from prepare_rates import SAST,COINS,cmc,kraken,Block
from render_rates import render

def main():
    now=datetime.now(SAST)
    key=os.environ.get("CMC_API_KEY","").strip()
    if not key: raise Block("CMC_API_KEY missing")
    a=cmc(key)
    b=kraken()
    used_at=datetime.now(SAST)
    results,values={},{}
    earliest_expiry=None
    for sym,(_,_,limit) in COINS.items():
        p,q=a[sym],b[sym]
        diff=100*abs(p["usd"]-q["usd"])/p["usd"]
        if diff>limit: raise Block(sym+" source mismatch")
        timestamps=[datetime.fromisoformat(x["updated_sast"]) for x in [p,q]]
        expiry=min(timestamps)+timedelta(minutes=5)
        earliest_expiry=expiry if earliest_expiry is None else min(earliest_expiry,expiry)
        values[sym]=p["usd"]
        results[sym]={"display_usd":round(p["usd"],2),"coinmarketcap":p,"kraken":q,
                      "deviation_pct":round(diff,5),"threshold_pct":limit}
    if (earliest_expiry-used_at).total_seconds()<90:
        raise Block("Insufficient remaining price validity for safe scheduling")
    directory=Path("docs/daily-rates")
    directory.mkdir(parents=True,exist_ok=True)
    today=used_at.date().isoformat()
    final=directory/(today+".png")
    audit=directory/(today+".json")
    if final.exists() or audit.exists(): raise Block("Duplicate official asset: stop")
    temporary=directory/("."+today+".tmp.png")
    try:
        display=render(values,used_at,temporary)
        done=datetime.now(SAST)
        if (earliest_expiry-done).total_seconds()<60: raise Block("Image not ready with sufficient freshness margin")
        digest=hashlib.sha256(temporary.read_bytes()).hexdigest()
        caption=(f"Your {done.day} {done.strftime('%B')} crypto price check 📊\n"
                 "$BTC, $ETH and $XMR.\n\n"
                 "No need to jump between exchanges.\n"
                 "Compare offers and swap in one place.\n"
                 "No account needed.\n\n👉 coinoswap.com\n\n")
        record={"status":"VALIDATED","approval_state":"PUBLICATION_APPROVED_NOT_YET_PUBLISHED",
                "date_sast":today,"checked_at_sast":done.isoformat(timespec="seconds"),
                "expires_at_sast":earliest_expiry.isoformat(timespec="seconds"),
                "coins":results,"display_prices":display,
                "image":{"filename":final.name,"sha256":digest,"width":1536,"height":1024},
                "caption":caption,
                "publication_note":"User explicitly authorized final live Facebook and Instagram test. Asset generation DOES NOT publish."}
        temporary.rename(final)
        audit.write_text(json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("OFFICIAL ASSET VERIFIED",final,"EXPIRES",earliest_expiry.isoformat())
    finally:
        temporary.unlink(missing_ok=True)

if __name__=="__main__":
    try: main()
    except (Block,KeyError,ValueError,FileNotFoundError) as e:
        print("FAIL CLOSED — NO PUBLISH",e,file=sys.stderr)
        sys.exit(2)
