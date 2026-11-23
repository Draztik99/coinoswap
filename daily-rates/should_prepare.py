"""GitHub Actions gate. Ignore the six unselected daily slots."""
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from posting_slots import slot_for_date, expected_prepare_time

now=datetime.now(ZoneInfo("Africa/Johannesburg"))
chosen=slot_for_date(now.date())
prep=expected_prepare_time(now.date())
target_minutes=chosen[0]*60+chosen[1]
now_minutes=now.hour*60+now.minute
prep_minutes=prep[0]*60+prep[1]
# Allow a delayed GitHub runner to start while there is still time to render.
# The renderer and independent publication watcher retain stricter cutoffs.
emergency=os.environ.get('EMERGENCY_RATES','').lower()=='true'
selected=emergency or (prep_minutes <= now_minutes < target_minutes-1)
print(f"Today {now.date()}: selected publication {chosen[0]:02}:{chosen[1]:02} SAST; preparing window {prep[0]:02}:{prep[1]:02} until one minute before target. Run at {now:%H:%M:%S} SAST. selected={selected}")
if 'GITHUB_OUTPUT' in os.environ:
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        f.write('selected='+('true' if selected else 'false')+'\n')
