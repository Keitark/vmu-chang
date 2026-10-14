#!/usr/bin/env python3
"""Tiny independent LC86K interpreter for VMU Stack-chan regression tests.
Not a full VMU emulator; checks our code path, input dispatch and VRAM copy only.
"""
from pathlib import Path
import json, struct, sys
BUILD=Path(__file__).resolve().parent
ROM=(BUILD/'STACKCHN.VMS').read_bytes()
FRAMES=(BUILD/'frames.bin').read_bytes()
SYM=json.loads((BUILD/'symbols.json').read_text())

def signed8(x):return x-256 if x&128 else x

class CPU:
 def __init__(self):
  self.ram=bytearray(512);self.banks=[bytearray(256) for _ in range(2)]
  self.pc=0;self.ninstr=0;self.current_key=0xff
  self.ram[0x14c]=0xff;self.ram[0x15c]=0
 def r(self,a):
  if a==0x14c:return self.current_key
  return self.ram[a]
 def w(self,a,v):
  if a==0x14c:return # P3 input is not affected by programming pull-ups
  self.ram[a]=v&255
 def fetch(self):
  v=ROM[self.pc];self.pc+=1;return v
 def direct(self,op):return ((op&1)<<8)|self.fetch()
 def jrel(self,off):self.pc=(self.pc+signed8(off))&0xffff
 def acc(self):return self.ram[0x100]
 def setacc(self,x):self.ram[0x100]=x&255
 def push(self,v):
  self.ram[0x106]=(self.ram[0x106]+1)&255
  self.ram[self.ram[0x106]]=v&255
 def pop(self):
  v=self.ram[self.ram[0x106]]
  self.ram[0x106]=(self.ram[0x106]-1)&255
  return v
 def step(self):
  self.ninstr+=1
  if self.ninstr>20000000:raise RuntimeError('instruction budget exceeded')
  addr=self.pc;op=self.fetch()
  if op==0x00:return
  if op==0x20:
   hi=self.fetch();lo=self.fetch();new=self.pc
   self.push(new&255);self.push(new>>8);self.pc=(hi<<8)|lo;return
  if op==0x21:self.pc=(self.fetch()<<8)|self.fetch();return
  if op==0xa0:
   hi=self.pop();lo=self.pop();self.pc=(hi<<8)|lo;return
  if op==0xb0:return
  if op==0xc1:
   tr=(self.r(0x105)<<8)|self.r(0x104)
   self.setacc(ROM[(tr+self.acc())&0xffff]);return
  if op in (0x02,0x03):self.setacc(self.r(self.direct(op)));return
  if op in (0x12,0x13):self.w(self.direct(op),self.acc());return
  if op in (0x22,0x23):
   d=self.direct(op);v=self.fetch();self.w(d,v);return
  if op in (0x62,0x63):
   d=self.direct(op);self.w(d,self.r(d)+1);return
  if op in (0x72,0x73):
   d=self.direct(op);self.w(d,self.r(d)-1);return
  if op in (0x60,0x61):self.push(self.r(self.direct(op)));return
  if op in (0x70,0x71):self.w(self.direct(op),self.pop());return
  if op in (0x82,0x83):self.setacc(self.acc()+self.r(self.direct(op)));return
  if op==0x81:self.setacc(self.acc()+self.fetch());return
  if op==0xe1:self.setacc(self.acc()&self.fetch());return
  if op==0x01:self.jrel(self.fetch());return
  if op==0x80:
   n=self.fetch()
   if self.acc()==0:self.jrel(n)
   return
  if op==0x90:
   n=self.fetch()
   if self.acc()!=0:self.jrel(n)
   return
  if op in (0x31,0x41):
   val=self.fetch();off=self.fetch()
   if (self.acc()==val)==(op==0x31):self.jrel(off)
   return
  if op in (0x32,0x33,0x42,0x43):
   d=self.direct(op);off=self.fetch()
   if (self.acc()==self.r(d))==(op in (0x32,0x33)):self.jrel(off)
   return
  if (op&0xe8) in (0x68,0x78,0x88,0x98):
   # opcode 011d1bbb=bp, 100d1bbb=bn
   mode=(op>>5)&7;d=(((op>>4)&1)<<8)|self.fetch();off=self.fetch();bit=op&7
   selected=bool(self.r(d)&(1<<bit))
   if selected==(mode==3):self.jrel(off)
   return
  if (op&0xe8) in (0xc8,0xd8,0xe8,0xf8,0xa8,0xb8):
   group=op&0xe8;d=(((op>>4)&1)<<8)|self.fetch();bit=op&7
   v=self.r(d)
   if group in (0xc8,0xd8):v &=~(1<<bit)
   elif group in (0xe8,0xf8):v |= 1<<bit
   else:v^=1<<bit
   self.w(d,v);return
  if op in (0x52,0x53):
   d=self.direct(op);off=self.fetch()
   self.w(d,self.r(d)-1)
   if self.r(d):self.jrel(off)
   return
  if op in (0x06,0x16):
   pointer=self.r(2)
   if pointer<0x80:raise RuntimeError('unexpected indirect below 0x80')
   bank=self.r(0x125)&1
   if op==0x16:self.banks[bank][pointer]=self.acc()
   else:self.setacc(self.banks[bank][pointer])
   return
  raise RuntimeError(f'UNIMPLEMENTED opcode {op:02x} @ {addr:04x}')
 def lcd(self):
  out=bytearray()
  for bank in self.banks:
   for ptr in range(0x80,0x100,16):out+=bank[ptr:ptr+12]
  assert len(out)==192
  return bytes(out)


def test():
 c=CPU()
 frame_ids=[]
 # A at frame 40, B 67, UP 94, DOWN 121, LEFT 148, RIGHT 175
 trigger={40:(0xEF,8),67:(0xDF,12),94:(0xFE,16),121:(0xFD,20),148:(0xFB,24),175:(0xF7,28)}
 prev=0
 target=206
 frames=0
 # Respond to frame draws just before delay begins
 while frames<target:
  if c.pc==SYM['main_loop']:
   c.current_key=trigger.get(frames,(0xff,None))[0]
  if c.pc==SYM['wait_frame']:
   fid=c.r(0x20)
   frame_ids.append(fid)
   actual=c.lcd();expect=FRAMES[fid*192:(fid+1)*192]
   if actual!=expect:
    first=next(i for i,(a,b) in enumerate(zip(actual,expect)) if a!=b)
    raise AssertionError(f'VRAM bad at frame {frames}, id {fid}, byte {first}: {actual[first]:02x} vs {expect[first]:02x} (total diff {sum(x!=y for x,y in zip(actual,expect))})')
   frames+=1
  c.step()
 print('Verified',len(frame_ids),'machine-executed frames;',c.ninstr,'LC86K instructions')
 for n,(btn,fid) in trigger.items():
  print(' Press at frame',n,'-> frames',frame_ids[n:n+6], 'expected',fid)
  if frame_ids[n]!=fid:raise AssertionError(f'wrong button at {n}: {frame_ids[n]} != {fid}')
 assert all(idx in frame_ids for idx in (2,3,4,5,6,7))
 print('PASS: direct LCD RAM write, timed idle animation, blink/glance, six button reactions')

if __name__=='__main__':test()
