from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

BASE=Path(__file__).parent
FONT='/usr/share/fonts/truetype/lato/Lato-Black.ttf'
FONT_DATE='/usr/share/fonts/truetype/lato/Lato-Bold.ttf'
MONTHS='JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split()
CARDS={'BTC':(98,492,295),'ETH':(575,967,771),'XMR':(1047,1436,1243)}

def render(prices,date,output):
    path=BASE/'assets'/'coinoswap_template.png'
    if not path.is_file(): raise ValueError('Official 1536x1024 template missing')
    with Image.open(path) as raw: im=raw.convert('RGBA')
    if im.size!=(1536,1024): raise ValueError('Unexpected template size')
    d=ImageDraw.Draw(im)
    d.rectangle((1215,87,1398,137),fill=(10,9,8,255))
    d.text((1304,109),f'{date.day} {MONTHS[date.month-1]}',
           font=ImageFont.truetype(FONT_DATE,37),fill='white',anchor='mm')
    result={}
    for sym,(left,right,center) in CARDS.items():
        price=float(prices[sym])
        if not 0<price<10000000: raise ValueError('Bad price for '+sym)
        y0,y1=768,862
        top=[im.getpixel((x,y0-5)) for x in range(left,right+1)]
        bottom=[im.getpixel((x,y1+5)) for x in range(left,right+1)]
        pix=im.load()
        for y in range(y0,y1+1):
            t=(y-y0)/(y1-y0)
            for j,x in enumerate(range(left,right+1)):
                pix[x,y]=tuple(round(top[j][k]*(1-t)+bottom[j][k]*t) for k in range(4))
        label='$'+f'{price:,.2f}'
        for sz in range(76,43,-1):
            font=ImageFont.truetype(FONT,sz)
            if d.textbbox((0,0),label,font=font)[2]<=right-left-2: break
        else: raise ValueError('Price too wide for '+sym)
        ImageDraw.Draw(im).text((center,817),label,font=font,fill='white',anchor='mm')
        result[sym]=label
    output.parent.mkdir(parents=True,exist_ok=True)
    im.convert('RGB').save(output,'PNG',optimize=True)
    return result
