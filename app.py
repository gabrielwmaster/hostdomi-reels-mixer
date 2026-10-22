"""HOSTDOMI: ONE STILL IMAGE + Spanish MP3 -> Reels-compatible MP4.
No generative video. Publishes nothing; private internal n8n/Dokploy worker.
"""
import io
import json
import os
import math
import hmac
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from PIL import Image, ImageDraw, ImageFont, ImageOps

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
SECRET = os.getenv('MIXER_API_KEY', '')
LOGO = Path(os.getenv('HOSTDOMI_LOGO_PATH', '/app/assets/logo.png'))
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
NAVY = (9, 20, 48)
ORANGE = (255, 140, 51)
YELLOW = (255, 213, 58)
LIME = (154, 215, 73)
WHITE = (247, 250, 255)


def font(sz, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, sz)


def fit_single_line(draw, text, width, size, minimum=27, bold=True):
    while size > minimum and draw.textbbox((0,0), text, font=font(size, bold))[2] > width:
        size -= 2
    return font(size,bold)


def wrap_lines(draw, text, maxw, f, maxlines=None):
    result=[]
    for segment in str(text).replace('\r','').split('\n'):
        current=''
        for word in segment.split():
            candidate=(current+' '+word).strip()
            if current and draw.textbbox((0,0),candidate,font=f)[2] > maxw:
                result.append(current)
                current=word
            else:current=candidate
        if current:result.append(current)
    if maxlines is not None:return result[:maxlines]
    return result


def make_art(base_file, title, subtitle, bullets, cta, target):
    with Image.open(base_file) as im:
        im = ImageOps.fit(im.convert('RGB'), (1080,1920), method=Image.Resampling.LANCZOS, centering=(0.5,0.5))
    # Dark overlay improves small-screen readability; keeps generated scene behind text.
    shade=Image.new('RGBA', (1080,1920), (0,0,0,0))
    pix=shade.load()
    for yy in range(1920):
        opacity = int(182 + 42*abs(yy-900)/1000)
        opacity = min(220, max(160,opacity))
        for xx in range(1080):
            pix[xx,yy]=(NAVY[0],NAVY[1],NAVY[2], opacity)
    # RGBA composite
    im=Image.alpha_composite(im.convert('RGBA'),shade)
    d=ImageDraw.Draw(im)
    if LOGO.exists():
        try:
            with Image.open(LOGO) as logo:
                logo=logo.convert('RGBA')

                # Aumentamos el área máxima permitida
                target_w = 650
                target_h = 150

                # Calculamos la proporción para que encaje perfecto sin deformarse
                ratio = min(target_w / logo.width, target_h / logo.height)
                new_size = (int(logo.width * ratio), int(logo.height * ratio))

                # resize() sí amplía la imagen, a diferencia de thumbnail()
                logo = logo.resize(new_size, Image.Resampling.LANCZOS)

                # Nuevas coordenadas (120 mueve el logo hacia arriba)
                logo_x = (1080 - logo.width) // 2
                logo_y = 120

                # Fondo blanco detrás del logo para que no se pierda (elimina estas 6 líneas si usas un logo blanco)
                padding = 25
                d.rounded_rectangle(
                    (logo_x - padding, logo_y - padding, logo_x + logo.width + padding, logo_y + logo.height + padding), 
                    radius=15, 
                    fill=(255, 255, 255, 230)
                )

                im.alpha_composite(logo,((1080-logo.width)//2,290))
        except Exception as e:
            raise ValueError('Logo oficial inválido: '+str(e))
    else:
        d.text((110,300),'HOSTDOMI',font=font(70),fill=WHITE)
        d.text((114,378),'TECNOLOGÍA · MARKETING · WEB',font=font(20,False),fill=(222,228,240,255))
    # Eyebrow + title only in central safe area
    d.text((110,560),'IDEAS PARA CRECER ONLINE',font=font(26),fill=LIME+(255,))
    title=str(title).upper().strip()
    f=font(80)
    lines=wrap_lines(d,title,865,f,maxlines=4)
    while len(lines)>3 and f.size>48:
        f=font(f.size-5)
        lines=wrap_lines(d,title,865,f,maxlines=4)
    y=620
    for s in lines[:3]:
        d.text((105,y),s,font=f,fill=WHITE,stroke_width=1,stroke_fill=NAVY)
        y+=f.size+14
    # Subheading
    subf=font(40,False)
    y=max(y+28,925)
    sub_lines=wrap_lines(d,str(subtitle),865,subf,2)
    for s in sub_lines:
        d.text((110,y),s,font=subf,fill=(223,235,249,255))
        y+=58
    y+=38
    for i,entry in enumerate(bullets[:4]):
        if y>1385:break
        d.rounded_rectangle((108,y+4,154,y+50),radius=14,fill=ORANGE+(255,))
        num=font(22)
        d.text((118,y+15),f'{i+1:02d}',font=num,fill=NAVY)
        bf=fit_single_line(d,str(entry),772,37,minimum=25)
        d.text((176,y+4),str(entry),font=bf,fill=WHITE)
        y+=85
    # CTA protected from bottom controls: keep above y 1510
    d.rounded_rectangle((103,1450,977,1522),radius=19,fill=ORANGE+(255,))
    caption=(str(cta).strip() or 'Conoce más en hostdomi.com')[:80]
    cf=fit_single_line(d,caption,810,34,minimum=22)
    bb=d.textbbox((0,0),caption,font=cf)
    d.text(((1080-(bb[2]-bb[0]))//2,1466),caption,font=cf,fill=NAVY)
    d.text((110,1560),'hostdomi.com',font=font(36),fill=YELLOW+(255,))
    # Nothing in the bottom 290 px safe zone.
    im.convert('RGB').save(target,'PNG',optimize=True)


def duration_of(filename):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration','-show_entries','format=duration','-of','json',str(filename)],capture_output=True,text=True,timeout=30)
    if p.returncode:raise ValueError('ffprobe no reconoce la locución: '+p.stderr[-500:])
    o=json.loads(p.stdout)
    d=float(o.get('format',{}).get('duration') or (o.get('streams') or [{}])[0].get('duration') or 0)
    return d


@app.get('/health')
async def health():
    return {'ok':True,'mode':'one-static-image-plus-audio','logo_loaded':LOGO.exists()}


@app.post('/compose')
async def compose(image:UploadFile=File(...),audio:UploadFile=File(...),title:str=Form(...),subtitle:str=Form(''),bullets_json:str=Form('[]'),cta:str=Form('Conoce más en hostdomi.com'),x_mixer_key:str|None=Header(None)):
    if not SECRET or not x_mixer_key or not hmac.compare_digest(x_mixer_key, SECRET):
        raise HTTPException(401,'X-Mixer-Key incorrecta o MIXER_API_KEY no configurada')
    work=Path(tempfile.mkdtemp(prefix='hostdomi-reel-'))
    try:
        pic=work/'input.png'
        snd=work/'voice.mp3'
        art=work/'composed.png'
        mov=work/'output.mp4'
        for upload,dest,limit in [(image,pic,32*1024*1024),(audio,snd,20*1024*1024)]:
            total=0
            with dest.open('wb') as f:
                while part:=await upload.read(1024*1024):
                    total+=len(part)
                    if total>limit:raise HTTPException(413,'Archivo demasiado grande')
                    f.write(part)
            if total<1024:raise ValueError('Archivo de entrada vacío')
        try:bullets=json.loads(bullets_json)
        except ValueError:raise HTTPException(400,'bullets_json no es un array JSON')
        if not isinstance(bullets,list):raise HTTPException(400,'bullets_json debe ser array')
        length=duration_of(snd)
        # No truncated / dubbed / missing speech allowed. Audio must be within 15-25s.
        if not 15<=length<=25:raise HTTPException(422,f'Audio debe durar 15–25 segundos; recibido: {length:.2f}s. Ajusta spoken_es en ChatGPT.')
        make_art(pic,title[:120],subtitle[:160],[str(s)[:80] for s in bullets],cta[:95],art)
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-loop','1','-framerate','30','-i',str(art),'-i',str(snd),'-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-r','30','-c:a','aac','-b:a','160k','-ar','48000','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-shortest','-movflags','+faststart','-t','25',str(mov)]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=200)
        if proc.returncode or not mov.exists() or mov.stat().st_size<20000:raise ValueError('No se generó MP4 válido: '+proc.stderr[-900:])
        return FileResponse(mov,media_type='video/mp4',filename='hostdomi-reel.mp4',background=BackgroundTask(shutil.rmtree,work,ignore_errors=True))
    except HTTPException:
        shutil.rmtree(work,ignore_errors=True);raise
    except Exception as err:
        shutil.rmtree(work,ignore_errors=True)
        raise HTTPException(422,str(err))
