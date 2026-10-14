#!/usr/bin/env python3
"""Native LC86K VMU assembler + VMS / VMI packager (Python stdlib only).
Outputs a real standalone VMU game, not a Dreamcast executable.
"""
from __future__ import annotations
from pathlib import Path
import struct, ast, re, datetime, json, sys
ROOT=Path(__file__).resolve().parent
BUILD=ROOT; BUILD.mkdir(exist_ok=True)

SFR={
 'ACC':0x100,'B':0x102,'C':0x103,'SP':0x106,'PCON':0x107,
 'IE':0x108,'EXT':0x10D,'OCR':0x10E,'PSW':0x101,
 'MCR':0x120,'TRL':0x104,'TRH':0x105, # hardware SFRs
 'XBNK':0x125,'VCCR':0x127,'P3':0x14C,'P3INT':0x14E,
 'P1':0x144,'P7':0x15C,
 'FRAME':0x20,'PHASE':0x21,'TTL':0x22,'BASE':0x23,'KEYCUR':0x24,'KEYLAST':0x25,
 'INDEX':0x26,'PTRLO':0x27,
}
# NOTE: TRL/TRH actual addresses from hardware are 0x104 / 0x105.

ASSEMBLY=r'''
; VMU STACKCHAN  - built for the REAL Dreamcast Visual Memory Unit.
@REGS@
; 48x32 monochrome LCD, LC86K CPU. Game is entirely standalone.
; A: MNYA  B: HEART  UP: HI!  DOWN: ZZZ  LEFT: NO  RIGHT: YES
; MODE: return to VMU menu. SLEEP: normal sleep behavior.
;
; Inspired by the official M5Stack-Avatar's eye/mouth geometry and expressions.
;
; Interrupt/reset vectors (game programs are mapped to address $0000).
.org $0000
    jmpf start
.org $0003
    reti
.org $000B
    reti
.org $0013
    reti
.org $001B
    jmpf timer_int
.org $0023
    reti
.org $002B
    reti
.org $0033
    reti
.org $003B
    reti
.org $0043
    reti
.org $004B
    clr1 P3INT, 0
    clr1 P3INT, 1
    reti

.org $0130
; VMU firmware clock interrupt trampoline, as used by VMUPet / Serpent.
timer_int:
    push IE
    clr1 IE, 7
    not1 EXT, 0
    jmpf timer_int
    pop IE
    reti

.org $01F0
goodbye:
    not1 EXT, 0
    jmpf goodbye

.org $0200
.text 16 "VMU STACK-CHAN"
.text 32 "STACK-CHAN MINI COMPANION"
.string 16 "VMUSTACK"
.org $0240
.word 1,16
.org $0260
; 16-color ARGB4444 icon palette, VMS header format
@PALETTE@
.org $0280
; 32x32 4bpp Dreamcast VMU file-manager icon (512 bytes)
@ICON@

.org $0480
start:
    clr1 IE, 7
    mov #$80, SP
    mov #$a1, OCR
    mov #$09, MCR
    mov #$80, VCCR
    mov #$ff, P3
    clr1 P3INT, 0
    clr1 P3INT, 1
    clr1 P1, 7
    mov #0, XBNK
    mov #0, PHASE
    mov #0, TTL
    mov #0, FRAME
    mov #$3F, KEYLAST
    set1 IE, 7
main_loop:
    callf keys
    callf choose_frame
    callf present
    callf wait_frame
    inc PHASE
    ld TTL
    bz next_frame
    dec TTL
next_frame:
    jmpf main_loop

; Hardware input: Port 3 bits 0-5 active-low:
; 0 UP,1 DOWN,2 LEFT,3 RIGHT,4 A,5 B.
keys:
    bp P7,0,keys_quit
    ld P3
    bn ACC,6,keys_quit
    bn ACC,7,keys_sleep
    and #$3f
    st KEYCUR
    ld KEYLAST
    be KEYCUR,keys_ret
    ld KEYCUR
    st KEYLAST
    be #$3f,keys_ret
    bn ACC,4,keys_a
    bn ACC,5,keys_b
    bn ACC,0,keys_up
    bn ACC,1,keys_down
    bn ACC,2,keys_left
    bn ACC,3,keys_right
keys_ret:
    ret
keys_a:
    mov #8, BASE
    jmpf reaction
keys_b:
    mov #12, BASE
    jmpf reaction
keys_up:
    mov #16, BASE
    jmpf reaction
keys_down:
    mov #20, BASE
    jmpf reaction
keys_left:
    mov #24, BASE
    jmpf reaction
keys_right:
    mov #28, BASE
    jmpf reaction
reaction:
    mov #16, TTL
    mov #0, PHASE
    ret
keys_quit:
    jmpf goodbye
keys_sleep:
    bn P3,7,keys_sleep
    mov #0, VCCR
sleep_more:
    set1 PCON,0
    bp P7,0,keys_quit
    bp P3,7,sleep_more
    mov #$80,VCCR
sleep_release:
    bn P3,7,sleep_release
    ret

choose_frame:
    ld TTL
    bz choose_idle
    ld PHASE
    and #$03
    add BASE
    st FRAME
    ret
choose_idle:
    ld PHASE
    and #$1f
    st PHASE
    be #10,choose_half
    be #11,choose_blink
    be #12,choose_half
    be #15,choose_tilt
    be #19,choose_left
    be #20,choose_left
    be #25,choose_right
    be #26,choose_right
    be #30,choose_smile
    and #1
    st FRAME
    ret
choose_tilt:
    mov #7,FRAME
    ret
choose_half:
    mov #2,FRAME
    ret
choose_blink:
    mov #3,FRAME
    ret
choose_left:
    mov #4,FRAME
    ret
choose_right:
    mov #5,FRAME
    ret
choose_smile:
    mov #6,FRAME
    ret

; Frame pointers are 16-bit little endian, 32 sprites x 192 bytes.
; Fetch an indexed pointer using the VMU Table Reference registers, then
; paint the chosen full-screen mono sprite to both LCD XRAM banks.
present:
    mov #<frame_table, TRL
    mov #>frame_table, TRH
    ld FRAME
    add FRAME
    st INDEX
    ld INDEX
    ldc
    st PTRLO
    inc INDEX
    ld INDEX
    ldc
    st TRH
    ld PTRLO
    st TRL
    callf paint
    ret

paint:
    clr1 OCR,5
    push ACC
    push XBNK
    push C
    push 2
    mov #$80, 2
    mov #0, XBNK
    mov #0, C
    ld C               ; REQUIRED: first LDC offset must be zero
paint_loop:
    ldc
    st @R2
    inc 2
    ld 2
    and #$0f
    bne #$0c,paint_no_gap
    ld 2
    add #4
    st 2
    bnz paint_no_gap
    inc XBNK
    mov #$80, 2
paint_no_gap:
    inc C
    ld C
    bne #$c0,paint_loop
    pop 2
    pop C
    pop XBNK
    pop ACC
    set1 OCR,5
    ret

wait_frame:
    push B
    push C
    mov #12,B
wait_outer:
    mov #0,C
wait_inner:
    dbnz C,wait_inner
    dbnz B,wait_outer
    pop C
    pop B
    ret

frame_table:
@POINTERS@

; 32 frame bitmaps, 6 bytes/row, 32 rows = 192 bytes each.
@FRAMES@
.cnop 0,$200
'''


def build_source() -> str:
    frames=(BUILD/'frames.bin').read_bytes(); icon=(BUILD/'icon.bin').read_bytes()
    assert len(frames)==32*192 and len(icon)==512
    def bytelines(buf,bytes_per_line=16):
        return '\n'.join('    .byte '+', '.join(f'${b:02X}' for b in buf[i:i+bytes_per_line]) for i in range(0,len(buf),bytes_per_line))
    palettes=bytes().join(struct.pack('<H',v) for v in [0xf000,0xffff,0xf777,0xf333,0xfeee,0xf000]+[0xf000]*10)
    pointers='\n'.join('    .word '+','.join(f'frame{i+j:02}' for j in range(min(8,32-i))) for i in range(0,32,8))
    frame_src='\n\n'.join(f'frame{i:02}:\n'+bytelines(frames[i*192:(i+1)*192]) for i in range(32))
    regs='\n'.join(f'{name} = ${addr:03X}' for name,addr in sorted(SFR.items()))
    src=ASSEMBLY.replace('@REGS@',regs).replace('@PALETTE@',bytelines(palettes)).replace('@ICON@',bytelines(icon)).replace('@POINTERS@',pointers).replace('@FRAMES@',frame_src)
    (ROOT/'stackchan.s').write_text(src,encoding='utf-8')
    return src


def value(expression, symbols, tolerate_unknown=False):
    expression=expression.strip()
    if expression.startswith('#'): expression=expression[1:]
    hi_lo=None
    if expression.startswith('<'):
        hi_lo='lo';expression=expression[1:]
    elif expression.startswith('>'):
        hi_lo='hi';expression=expression[1:]
    expression=re.sub(r'\$([a-fA-F0-9]+)',lambda m:str(int(m.group(1),16)),expression)
    expression=re.sub(r'%([01]+)',lambda m:str(int(m.group(1),2)),expression)
    try:
        t=ast.parse(expression,mode='eval')
        def walk(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,int):return node.value
            if isinstance(node,ast.Name):
                if node.id in symbols:return symbols[node.id]
                if tolerate_unknown:return 0
                raise KeyError(node.id)
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub):return -walk(node.operand)
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub)):
                a,b=walk(node.left),walk(node.right);return a+b if isinstance(node.op,ast.Add) else a-b
            raise ValueError('Unsupported expression '+expression)
        n=walk(t.body)
        if hi_lo=='lo':n&=0xff
        elif hi_lo=='hi':n=(n>>8)&0xff
        return n
    except Exception as exc:
        raise ValueError(f'Cannot parse {expression!r}: {exc}') from exc

def assemble(source:str)->tuple[bytes,dict]:
    lines=[]
    syms=dict(SFR)
    for n,raw in enumerate(source.splitlines(),1):
        line=raw.split(';',1)[0].strip()
        if not line:continue
        if ':' in line and re.match(r'^[A-Za-z_][\w]*:',line):
            label,line=line.split(':',1)
            lines.append((n,label+':'))
            line=line.strip()
        if line:
            m=re.fullmatch(r'([A-Za-z_][\w]*)\s*=\s*(.+)',line)
            if m:
                syms[m.group(1)]=value(m.group(2),syms)
            else:lines.append((n,line))
    def get_size(line,pc,first):
        if line.endswith(':'): return (0,[])
        if line.startswith('.'):
            cmd,_,arg=line.partition(' ');arg=arg.strip()
            if cmd=='.org':return(-1,[])
            if cmd=='.cnop':return(-2,[])
            if cmd=='.byte':return(len(arg.split(',')),[])
            if cmd=='.word':return(2*len(arg.split(',')),[])
            if cmd in ('.text','.string'):
                m=re.match(r'(\d+)\s+"(.*)"$',arg)
                if not m:raise ValueError(f'bad {cmd}: {line}')
                return(int(m.group(1)),[])
            raise ValueError('unknown directive '+cmd)
        cmd=line.split()[0].lower(); a=line[len(cmd):].strip();args=[z.strip() for z in a.split(',')] if a else []
        if cmd in ('reti','ret','nop','ldc'):return(1,args)
        if cmd in ('callf','jmpf'):return(3,args)
        if cmd in ('br','bz','bnz'):return(2,args)
        if cmd in ('be','bne'):
            assert len(args)==2
            return(3 if args[0].startswith('#') else 3,args)
        if cmd in ('bp','bn','clr1','set1','not1'):
            return(3 if cmd in ('bp','bn') else 2,args)
        if cmd=='dbnz':return(3,args)
        if cmd=='mov':return(3 if not args[1].startswith('@') else 2,args)
        if cmd in ('push','pop','ld','st','inc','dec','add','and','or','xor'):
            return(2 if not (cmd in ('ld','st') and args[0].startswith('@')) and not (cmd in ('add','and','or','xor') and args[0].startswith('@')) else 1,args)
        raise ValueError('unknown instruction: '+line)
    # Some instructions with registers have the direct addressing form;
    # i8 immediates are two bytes; d9 direct is two bytes.
    for first in (True,False):
        pc=0;out=bytearray(); errors=[]; emitted_labels={}
        for n,line in lines:
            try:
                if line.endswith(':'):
                    if first:syms[line[:-1]]=pc
                    emitted_labels[line[:-1]]=pc;continue
                if line.startswith('.org'):
                    target=value(line.split(None,1)[1],syms,first)
                    if target<pc:raise ValueError(f'.org backward target {target:#x} < {pc:#x}')
                    if not first:out.extend(bytes(target-pc))
                    pc=target;continue
                if line.startswith('.cnop'):
                    a,b=line.split(None,1)[1].split(','); offset=value(a,syms,first);mod=value(b,syms,first)
                    target=((pc+mod-1)//mod)*mod+offset
                    if not first:out.extend(bytes(target-pc))
                    pc=target;continue
                size,args=get_size(line,pc,first)
                if first:pc+=size;continue
                data=encode(line,pc,syms,args)
                if len(data)!=size:raise ValueError(f'size mismatch: expected {size}, emitted {len(data)}')
                out.extend(data);pc+=len(data)
            except Exception as e:
                raise ValueError(f'ASSEMBLY line {n}: {line} -> {e}') from e
        if not first: return bytes(out),syms
    raise AssertionError('No output')


def encode(line,pc,symbols,args):
    def v(i):return value(args[i],symbols)
    def b(n):
        if n<0 or n>255:raise ValueError(f'Out of byte range: {n}')
        return n
    def lo(n):return n&255
    def hi(n):return n>>8&255
    def rel(target,offset):
        d=target-(pc+offset)
        if not -128<=d<=127:raise ValueError(f'relative branch too far delta={d}')
        return d&255
    if line.startswith('.'):
        cmd,_,arg=line.partition(' ');arg=arg.strip()
        if cmd=='.byte':return bytes(b(value(s,symbols)) for s in arg.split(','))
        if cmd=='.word':return b''.join(struct.pack('<H',value(s,symbols)) for s in arg.split(','))
        if cmd in ('.text','.string'):
            m=re.match(r'(\d+)\s+"(.*)"$',arg)
            n=int(m.group(1));raw=m.group(2).encode('ascii')
            if len(raw)>n:raise ValueError('String too long')
            return raw.ljust(n,b' ' if cmd=='.text' else b'\x00')
        raise ValueError(cmd)
    cmd=line.split()[0].lower()
    if cmd in ('reti','ret','nop','ldc'):return bytes([{'reti':0xb0,'ret':0xa0,'nop':0x00,'ldc':0xc1}[cmd]])
    if cmd in ('callf','jmpf'):
        a=v(0)
        return bytes([0x20 if cmd=='callf' else 0x21,hi(a),lo(a)])
    if cmd in ('br','bz','bnz'):
        return bytes([{'br':1,'bz':0x80,'bnz':0x90}[cmd],rel(v(0),2)])
    if cmd in ('be','bne'):
        target=v(1)
        if args[0].startswith('#'):return bytes([0x31 if cmd=='be' else 0x41,b(v(0)),rel(target,3)])
        d=v(0)
        assert d<=0x1ff
        return bytes([(0x32 if cmd=='be' else 0x42)|(d>>8),lo(d),rel(target,3)])
    if cmd in ('bp','bn'):
        d,bit,target=v(0),v(1),v(2)
        return bytes([(0x68 if cmd=='bp' else 0x88)|((d>>8)<<4)|bit,lo(d),rel(target,3)])
    if cmd in ('clr1','set1','not1'):
        d,bit=v(0),v(1)
        return bytes([{'clr1':0xc8,'set1':0xe8,'not1':0xa8}[cmd]|((d>>8)<<4)|bit,lo(d)])
    if cmd=='dbnz':
        d=v(0)
        return bytes([0x52|(d>>8),lo(d),rel(v(1),3)])
    if cmd=='mov':
        imm=v(0)
        if args[1].startswith('@'):return bytes([0x24|int(args[1][-1]),b(imm)])
        d=v(1)
        return bytes([0x22|(d>>8),lo(d),b(imm)])
    base={'push':0x60,'pop':0x70,'ld':0x02,'st':0x12,'inc':0x62,'dec':0x72,'add':0x82,'and':0xe2,'or':0xd2,'xor':0xf2}
    if cmd in base:
        if args[0].startswith('@'):
            # Only register R2 referenced by generated game in LD/ST.
            if cmd=='ld':return bytes([0x04|int(args[0][-1])])
            if cmd=='st':return bytes([0x14|int(args[0][-1])])
            raise ValueError('not implemented indirect '+line)
        if args[0].startswith('#'):
            op={'add':0x81,'and':0xe1,'or':0xd1,'xor':0xf1}.get(cmd)
            if op is None:raise ValueError('immediate form not available '+line)
            return bytes([op,b(v(0))])
        d=v(0)
        return bytes([base[cmd]|(d>>8),lo(d)])
    raise ValueError('Unhandled: '+cmd)


def make_vmi(vms:bytes):
    name=b'STACKCHN';file_name=b'STACKCHAN'
    vmi=bytearray(108)
    vmi[0:4]=bytes(n & s for n,s in zip(name[:4],b'SEGA'))
    vmi[4:36]=b'Stack-chan companion for VMU'.ljust(32,b'\0')
    vmi[36:68]=b'Stackchan VMU fan homebrew'.ljust(32,b'\0')
    now=datetime.datetime(2026,10,14,0,0,0)
    struct.pack_into('<HBBBBBB',vmi,0x44,now.year,now.month,now.day,now.hour,now.minute,now.second,(now.weekday()+1)%7)
    struct.pack_into('<HH',vmi,0x4c,0,1)
    vmi[0x50:0x58]=name
    vmi[0x58:0x64]=file_name.ljust(12,b'\0')
    struct.pack_into('<H',vmi,0x64,0x0002) # game (not protected)
    struct.pack_into('<I',vmi,0x68,len(vms))
    assert len(vmi)==108
    return bytes(vmi)

def main():
    source=build_source()
    binary,symbols=assemble(source)
    assert len(binary)%512==0
    assert binary[0]==0x21
    assert binary[0x200:0x210].startswith(b'VMU STACK-CHAN')
    assert symbols['start']==0x480
    assert binary[symbols['frame00']:symbols['frame00']+192]==(BUILD/'frames.bin').read_bytes()[:192]
    assert binary[0x280:0x480]==(BUILD/'icon.bin').read_bytes()
    (BUILD/'STACKCHN.VMS').write_bytes(binary)
    (BUILD/'STACKCHN.VMI').write_bytes(make_vmi(binary))
    (BUILD/'symbols.json').write_text(json.dumps(symbols,indent=2))
    print('VMU code and assets assembled!')
    print('VMU bytes',len(binary),'blocks',len(binary)//512)
    for name in ['start','keys','choose_frame','present','paint','frame_table','frame00','frame31']:
        print(f' {name:14} 0x{symbols[name]:04X}')
    print('VMU program:',BUILD/'STACKCHN.VMS')
    print('VMI transfer:',BUILD/'STACKCHN.VMI')

if __name__=='__main__':main()
