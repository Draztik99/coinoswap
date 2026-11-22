"""Deterministic, auditable weekly randomization: each of seven slots once/week."""
import hashlib
import random
from datetime import timedelta

SLOTS=((11,30),(12,0),(12,30),(13,0),(13,30),(14,0),(14,30))

def slot_for_date(day):
    monday=day-timedelta(days=day.weekday())
    seed=hashlib.sha256(("CoinoSwap|DailyRates|"+monday.isoformat()).encode()).digest()
    sequence=list(range(len(SLOTS)))
    random.Random(int.from_bytes(seed[:8],"big")).shuffle(sequence)
    hour,minute=SLOTS[sequence[day.weekday()]]
    return hour,minute

def expected_prepare_time(day):
    hour,minute=slot_for_date(day)
    minutes=hour*60+minute-4
    return minutes//60,minutes%60

if __name__=="__main__":
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now=datetime.now(ZoneInfo("Africa/Johannesburg"))
    print(f"CoinoSwap {now.date()}: publish {slot_for_date(now.date())[0]:02}:{slot_for_date(now.date())[1]:02} SAST; prepare {expected_prepare_time(now.date())[0]:02}:{expected_prepare_time(now.date())[1]:02} SAST")
