"""GitHub Actions gate. Ignore the six unselected daily slots."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from posting_slots import slot_for_date, expected_prepare_time

now=datetime.now(ZoneInfo("Africa/Johannesburg"))
chosen=slot_for_date(now.date())
prep=expected_prepare_time(now.date())
selected=((now.hour,now.minute)==prep or (now.hour,now.minute)==(prep[0],prep[1]+1))
print(f"Today {now.date()}: selected publication {chosen[0]:02}:{chosen[1]:02} SAST; preparing window {prep[0]:02}:{prep[1]:02}-{prep[1]+1:02}. Run at {now:%H:%M:%S} SAST. selected={selected}")
if 'GITHUB_OUTPUT' in os.environ:
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        f.write('selected='+('true' if selected else 'false')+'\n')
