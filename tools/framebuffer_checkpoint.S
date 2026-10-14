/* Standalone SH-4 diagnostic helper. Does not modify IP.BIN or video mode.
 * r4 = stage 1..6; saves r0-r14, SR and PR; MAC/FPU/GBR/VBR untouched.
 * Cumulative 32x8 color blocks in each displayed field at x=32+40*(stage-1),
 * y=32 field-lines. Stage: red, yellow, green, cyan, magenta (failure),
 * blue (optional post-CCR/native-P2 guard).
 * PVR FB_R_CTRL/SOF1/SOF2/SIZE definitions verified against Flycast v2.7
 * and local pinned KOS 2.2.1 video.c/pvr_regs.h. All writes use uncached P2.
 * A marker is an observation before a jump, not proof of execution afterward.
 */
    .section .text
    .align 2
    .global _vmu_checkpoint
_vmu_checkpoint:
    mov.l r0,@-r15
    mov.l r1,@-r15
    mov.l r2,@-r15
    mov.l r3,@-r15
    mov.l r4,@-r15
    mov.l r5,@-r15
    mov.l r6,@-r15
    mov.l r7,@-r15
    mov.l r8,@-r15
    mov.l r9,@-r15
    mov.l r10,@-r15
    mov.l r11,@-r15
    mov.l r12,@-r15
    mov.l r13,@-r15
    mov.l r14,@-r15
    stc.l sr,@-r15
    sts.l pr,@-r15
    cmp/pl r4
    bt .Lpositive_stage
    bra .Lrestore
    nop
.Lpositive_stage:
    mov #6,r0
    cmp/hi r0,r4
    bf .Lvalid_stage
    bra .Lrestore
    nop
.Lvalid_stage:
    mov.l .Lpvr_base,r8
    mov #68,r0
    mov.l @(r0,r8),r0
    shlr2 r0
    and #3,r0
    mov r0,r9                  /* Framebuffer read depth: 0/1/2/3. */
    mov #92,r0
    mov.l @(r0,r8),r0
    mov r0,r10
    mov.l .Lmask10,r1
    and r1,r10                /* x_size: 32-bit words minus one. */
    mov r0,r2
    mov #-20,r0
    shld r0,r2
    and r1,r2                 /* modulus: skip words plus one. */
    add r2,r10
    shll2 r10                 /* Correct physical row stride bytes. */

    mov r4,r0
    add #-1,r0
    mov r0,r1
    shll2 r1
    shll r1                   /* stage index * 8 = palette offset. */
    mova .Lpalette,r0
    add r1,r0
    mov r0,r2
    mov r9,r0
    cmp/eq #0,r0
    bt .Lcolor555
    cmp/eq #1,r0
    bt .Lcolor565
    mov.l @(4,r2),r12
    cmp/eq #2,r0
    bt .Lbpp3
    mov #4,r7
    bra .Lposition
    nop
.Lcolor555:
    mov.w @r2,r12
    bra .Lbpp2
    nop
.Lcolor565:
    add #2,r2
    mov.w @r2,r12
.Lbpp2:
    mov #2,r7
    bra .Lposition
    nop
.Lbpp3:
    mov #3,r7
.Lposition:
    mov r4,r5
    add #-1,r5
    mov r5,r1
    shll2 r1
    shll r1
    shll2 r5
    shll2 r5
    shll r5
    add r1,r5
    add #32,r5                /* x pixel coordinate. */
    mov r5,r11
    shll r11
    mov r7,r0
    cmp/eq #2,r0
    bt .Lfields
    cmp/eq #3,r0
    bt .Lposition24
    shll r11
    bra .Lfields
    nop
.Lposition24:
    add r5,r11
.Lfields:
    mov r8,r14
    add #80,r14               /* FB_R_SOF1, then FB_R_SOF2. */
    mov #2,r13
.Lfield:
    mov.l @r14,r6
    mov.l .Lvram_mask,r0
    and r0,r6
    mov.l .Lvram_base,r0
    or r0,r6
    mov r10,r0
    shll2 r0
    shll2 r0
    shll r0                   /* y=32: row stride * 32. */
    add r0,r6
    add r11,r6
    mov #8,r3
.Lrow:
    mov r6,r1
    mov #32,r2
    mov r7,r0
    cmp/eq #2,r0
    bt .Lpixels16
    cmp/eq #3,r0
    bt .Lpixels24_setup
.Lpixels32:
    mov.l r12,@r1
    add #4,r1
    dt r2
    bf .Lpixels32
    bra .Lnextrow
    nop
.Lpixels16:
    mov.w r12,@r1
    add #2,r1
    dt r2
    bf .Lpixels16
    bra .Lnextrow
    nop
.Lpixels24_setup:
    /* Four packed RGB888 pixels occupy three aligned 32-bit words.
     * x=32+40n and stride are multiples of four: avoid byte VRAM writes.
     */
    mov r12,r0
    and #255,r0
    shll16 r0
    shll8 r0
    or r12,r0
    mov r0,r4                 /* B G R B bytes. */
    mov r12,r5
    shlr8 r5
    mov r12,r0
    shll16 r0
    or r0,r5                  /* G R B G bytes. */
    mov r12,r9
    shll8 r9
    mov r12,r0
    shlr16 r0
    or r0,r9                  /* R B G R bytes. */
    mov #8,r2
.Lpixels24:
    mov.l r4,@r1
    add #4,r1
    mov.l r5,@r1
    add #4,r1
    mov.l r9,@r1
    add #4,r1
    dt r2
    bf .Lpixels24
.Lnextrow:
    add r10,r6
    dt r3
    bf .Lrow
    add #4,r14
    dt r13
    bf .Lfield
.Lrestore:
    lds.l @r15+,pr
    ldc.l @r15+,sr
    mov.l @r15+,r14
    mov.l @r15+,r13
    mov.l @r15+,r12
    mov.l @r15+,r11
    mov.l @r15+,r10
    mov.l @r15+,r9
    mov.l @r15+,r8
    mov.l @r15+,r7
    mov.l @r15+,r6
    mov.l @r15+,r5
    mov.l @r15+,r4
    mov.l @r15+,r3
    mov.l @r15+,r2
    mov.l @r15+,r1
    rts
    mov.l @r15+,r0
    .align 2
.Lpvr_base: .long 0xa05f8000
.Lvram_base: .long 0xa5000000
.Lvram_mask: .long 0x007fffff
.Lmask10: .long 0x000003ff
.Lpalette:
    .word 0x7c00,0xf800
    .long 0x00ff0000
    .word 0x7fe0,0xffe0
    .long 0x00ffff00
    .word 0x03e0,0x07e0
    .long 0x0000ff00
    .word 0x03ff,0x07ff
    .long 0x0000ffff
    .word 0x7c1f,0xf81f
    .long 0x00ff00ff
    .word 0x001f,0x001f
    .long 0x000000ff
