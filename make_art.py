#!/usr/bin/env python3
"""Generate pixel-perfect 48x32 mono VMU frames and a 32x32 save icon.
Faithful low-resolution adaptation of the Stack-chan / M5Stack Avatar geometry.
No external images or third-party assets are embedded.
"""
from PIL import Image, ImageDraw
from pathlib import Path
import sys

W,H=48,32
OUT=Path(__file__).resolve().parent
BUILD=OUT
BUILD.mkdir(parents=True,exist_ok=True)
FONT={
 'A':["010","101","111","101","101"],
 'B':["110","101","110","101","110"],
 'E':["111","100","110","100","111"],
 'H':["101","101","111","101","101"],
 'I':["111","010","010","010","111"],
 'L':["100","100","100","100","111"],
 'M':["101","111","111","101","101"],
 'N':["101","111","111","111","101"],
 'O':["111","101","101","101","111"],
 'S':["111","100","111","001","111"],
 'Y':["101","101","010","010","010"],
 'Z':["111","001","010","100","111"],
 '!':["1","1","1","0","1"],
 '?':["111","001","010","000","010"],
 '.':["0","0","0","0","1"],
}

def pset(d,x,y,col=1):
 if 0<=x<W and 0<=y<H: d.point((x,y),fill=col)

def font(d,s,x,y,fill=1):
 for ch in s:
  glyph=FONT[ch]
  for ry,line in enumerate(glyph):
   for rx,v in enumerate(line):
    if v=='1':pset(d,x+rx,y+ry,fill)
  x+=len(glyph[0])+1

def heart(d,x,y,s=1):
 pat=['01010','11111','11111','01110','00100']
 for j,row in enumerate(pat):
  for i,p in enumerate(row):
   if p=='1':
    if s==1:pset(d,x+i,y+j)
    else:d.rectangle((x+i*s,y+j*s,x+i*s+s-1,y+j*s+s-1),fill=1)

def draw_face(d,x,y,w,h,expression='neutral',blink=0,mouth_open=0,gaze=0,breath=0):
 # Cast body to exact low-res form: 16:12 face and classic eyes/mouth
 # outline of the rounded display (outer shell) in black on pale VMU LCD
 d.rounded_rectangle((x,y,x+w-1,y+h-1),radius=3,outline=1,width=1)
 # Visually darker 'screen', leaving shell border; negative light eyes/face.
 d.rounded_rectangle((x+3,y+3,x+w-4,y+h-7),radius=2,fill=1)
 panel_left,panel_right=x+4,x+w-5
 # eye positions approximately from real M5Stack-Avatar: x90 and x230 on 320 width
 eyey=y+11+breath
 eye1=x+int(round(w*.295))+gaze
 eye2=x+int(round(w*.705))+gaze
 if expression=='sad': eyey+=1
 if expression=='sleepy':blink=2
 for k,ex in enumerate((eye1,eye2)):
  if expression in ('happy','laugh','heart'):
   # M5Stack Avatar happy eye: curved crescent
   for off in (-2,-1,0,1,2):
    pset(d,ex+off,eyey+(0 if abs(off)==2 else -1),0)
  elif expression=='angry':
   # inverse slanted narrowed eyes (triangle mask for Angry)
   for off in (-2,-1,0,1,2):pset(d,ex+off,eyey+((-off) if k==0 else off)//2,0)
  elif expression=='sad':
   for off in (-1,0,1):pset(d,ex+off,eyey+(off if k==0 else -off),0)
  elif blink==2:
   for off in (-2,-1,0,1,2):pset(d,ex+off,eyey,0)
  elif blink==1:
   d.line((ex-1,eyey,ex+1,eyey),fill=0)
   d.line((ex-1,eyey+1,ex+1,eyey+1),fill=0)
  else:
   radius=2 if expression=='surprise' else 1
   d.ellipse((ex-radius,eyey-radius,ex+radius,eyey+radius),fill=0)
 # mouth based on canonical thin white M5Stack-Avatar line
 mouthx=x+w//2
 mouthy=y+17+breath
 if expression in ('happy','laugh','heart') and not mouth_open:
  for off in range(-3,4):pset(d,mouthx+off,mouthy-(1 if abs(off)<=1 else 0),0)
 elif expression=='sad':
  for off in range(-3,4):pset(d,mouthx+off,mouthy+(1 if abs(off)<=1 else 0),0)
 elif expression=='surprise' or mouth_open==2:
  d.ellipse((mouthx-2,mouthy-2,mouthx+2,mouthy+2),fill=0)
  pset(d,mouthx,mouthy,1)
 elif mouth_open==1:
  d.rectangle((mouthx-3,mouthy-2,mouthx+3,mouthy+1),fill=0)
  d.line((mouthx-1,mouthy+1,mouthx+1,mouthy+1),fill=1)
 else:
  d.line((mouthx-3,mouthy,mouthx+3,mouthy),fill=0)
 # 3 small physical M5Stack buttons beneath display. Negative white on body.
 btn_y=y+h-4
 for dx in (-8,0,8):
  bx=x+w//2+dx
  d.rounded_rectangle((bx-3,btn_y,bx+2,btn_y+2),radius=1,fill=1)
  d.rectangle((bx-2,btn_y,bx+1,btn_y+1),fill=0)
 # Dark modular stand and two feet, identifying stack-chan body.
 base_mid=x+w//2
 d.rectangle((base_mid-3,y+h,base_mid+3,y+h),fill=1)
 d.rounded_rectangle((base_mid-13,y+h+1,base_mid-1,y+h+3),radius=1,fill=1)
 d.rounded_rectangle((base_mid+1,y+h+1,base_mid+13,y+h+3),radius=1,fill=1)


def speech_balloon(d,word,level=2):
 # White message bubble outlined in dark LCD pixels, tail pointing at face.
 # The narrow bubble width is intentionally 18px, preserving the real speech balloon style.
 if level==1:
  d.rounded_rectangle((35,7,47,13),radius=2,fill=0,outline=1)
  pset(d,34,12)
  pset(d,33,13)
  return
 x1,y1,x2,y2=29,3,47,16
 d.rounded_rectangle((x1,y1,x2,y2),radius=3,fill=0,outline=1)
 d.polygon([(x1,y1+8),(x1-4,y1+11),(x1,y1+11)],fill=0)
 d.line([(x1,y1+8),(x1-4,y1+11),(x1,y1+11)],fill=1)
 if word=='HEART':
  heart(d,36,7)
 else:
  total=sum(len(FONT[c][0]) for c in word)+len(word)-1
  font(d,word,31+(16-total)//2,7)


def create_image(expr='neutral',mode='idle',shift=0,bob=0,blink=0,gaze=0,mouth=0,speech='',balloon_level=2):
 img=Image.new('1',(W,H),0)
 d=ImageDraw.Draw(img)
 if mode=='idle':
  x,y,w,h=6+shift,2+bob,36,25
 else:
  x,y,w,h=0+shift,3+bob,31,24
 draw_face(d,x,y,w,h,expr,blink,mouth,gaze,bob if False else 0)
 if speech:
  speech_balloon(d,speech,balloon_level)
 return img

FRAMES=[]
def add(name,**kw):
 FRAMES.append((name,create_image(**kw)))

# 0..7 idle and autonomous animation, reference M5Stack Avatar's breathing and blinking
add('idle', mode='idle')
add('breathing',mode='idle',bob=1)
add('half-blink',mode='idle',blink=1)
add('closed-blink',mode='idle',blink=2)
add('glance-left',mode='idle',gaze=-2)
add('glance-right',mode='idle',gaze=2)
add('subtle-smile',mode='idle',expr='happy',bob=1)
add('tilt-idle',mode='idle',shift=-1)

# Six distinct reaction cycles (4 frames each), with head-bob / lip sync:
SEQUENCES=[
 ('A','MNYA','neutral',[0,1,2,0]),
 ('B','HEART','happy',[0,0,1,0]),
 ('UP','HI!','happy',[0,1,0,1]),
 ('DOWN','ZZZ','sleepy',[0,0,0,0]),
 ('LEFT','NO','angry',[0,0,0,0]),
 ('RIGHT','YES','happy',[0,1,0,0]),
]
for group,word,expr,mouths in SEQUENCES:
 for t in range(4):
  add(f'{group}-{t}',mode='speaking',expr=expr,shift=[0,1,0,-1][t],bob=[0,-1,0,1][t],
      gaze=[0,0,1,0][t] if group=='A' else 0,
      mouth=mouths[t],blink=0,speech=word,balloon_level=2 if t else 1)
assert len(FRAMES)==32

def as_vram(img):
 p=img.load(); out=bytearray()
 for y in range(H):
  for bx in range(6):
   val=0
   for k in range(8):val|=(1 if p[bx*8+k,y] else 0)<<(7-k)
   out.append(val)
 assert len(out)==192
 return bytes(out)


def create_icon():
 # Color save-manager icon, inspired by classic black-screen Stack-chan casing
 im=Image.new('RGB',(32,32),'#e5e5e5')
 d=ImageDraw.Draw(im)
 d.rounded_rectangle((3,2,28,25),radius=4,fill='#707070',outline='#3b3b3b',width=2)
 d.rounded_rectangle((5,4,26,20),radius=2,fill='#000000')
 for x in (11,21):d.ellipse((x-2,10,x+2,14),fill='white')
 d.rectangle((12,16,20,17),fill='white')
 for x in (10,15,20):d.rectangle((x,22,x+3,23),fill='#ffffff')
 d.rectangle((13,26,18,27),fill='#444444')
 d.rectangle((6,28,14,30),fill='#333333')
 d.rectangle((18,28,26,30),fill='#333333')
 return im

# generate 4bpp palette icon aligned with the header 16 x 2-byte colors.
PALETTE=[(0,0,0),(255,255,255),(119,119,119),(51,51,51),(230,230,230),(0,0,0)] + [(0,0,0)]*10
PALETTE_HEX=[0xF000,0xFFFF,0xF777,0xF333,0xFEEE,0xF000]+[0xF000]*10

def make_icon_bytes(im):
 out=bytearray()
 for y in range(32):
  for x in range(0,32,2):
   a=min(range(6),key=lambda idx:sum((PALETTE[idx][j]-im.getpixel((x,y))[j])**2 for j in range(3)))
   b=min(range(6),key=lambda idx:sum((PALETTE[idx][j]-im.getpixel((x+1,y))[j])**2 for j in range(3)))
   out.append((a<<4)|b)
 assert len(out)==512
 return bytes(out)

def main():
 # Store continuous frames in codegen-ready format and make human-visible previews.
 binary=b''.join(as_vram(im) for name,im in FRAMES)
 (BUILD/'frames.bin').write_bytes(binary)
 icon=create_icon()
 icon.save(BUILD/'icon.png')
 (BUILD/'icon.bin').write_bytes(make_icon_bytes(icon))
 # Compile a GIF using the same sequence plan as firmware.
 seq=[0,1,0,1,2,3,2,0,4,0,5,0,6,0]+sum(([i+(j%4) for j in range(8)]+[0,1] for i in (8,12,16,20,24,28)),[])
 gif_frames=[]
 for idx in seq:
  im=FRAMES[idx][1].convert('RGB')
  # Accentuate LCD colors using a readable high-contrast e-ink palette
  px=im.load()
  for yy in range(H):
   for xx in range(W):px[xx,yy]=(30,43,32) if FRAMES[idx][1].getpixel((xx,yy)) else (194,219,173)
  gif_frames.append(im.resize((576,384),Image.Resampling.NEAREST))
 gif_frames[0].save(BUILD/'preview.gif',save_all=True,append_images=gif_frames[1:],duration=200,loop=0,optimize=True)
 def lcd_preview(idx,scale=12):
  raw=FRAMES[idx][1]
  im=Image.new('RGB',(W,H))
  for yy in range(H):
   for xx in range(W):
    im.putpixel((xx,yy),(30,43,32) if raw.getpixel((xx,yy)) else (194,219,173))
  return im.resize((W*scale,H*scale),Image.Resampling.NEAREST)
 for idx in (0,3,8,9,12,16,20,24,28):
  lcd_preview(idx).save(BUILD/f'frame_{idx:02}.png')
 # Small collection of actual program frames, for easy design review.
 from PIL import ImageFont
 labels=['Idle','Blink','A - MNYA','B - Heart','Up - HI!','Down - ZZZ','Left - NO','Right - YES']
 ids=[0,3,9,13,17,21,25,29]
 tile_w=48*8; tile_h=32*8
 gallery=Image.new('RGB',(tile_w*2+48,tile_h*4+152),'#e5ebdb')
 gd=ImageDraw.Draw(gallery)
 for j,(label,idx) in enumerate(zip(labels,ids)):
  xx=(j%2)*(tile_w+16)+16;yy=(j//2)*(tile_h+31)+24
  gd.text((xx,yy-16),label,fill='#233b26')
  gallery.paste(lcd_preview(idx,8),(xx,yy))
 gallery.save(BUILD/'showcase.png')
 print('Frames:',len(FRAMES),'size',len(binary),'bytes')
 print('Descriptions:')
 for i,(n,_) in enumerate(FRAMES):print(f'  {i:2d}: {n}')

if __name__=='__main__':main()
