/*
 * VMU browser adapter entered by replacing its six initial NOPs with a
 * long jump. Assemble/link this section at the appended binary address.
 * The BOING/mkdcdisc IP.BIN stays unchanged and its normal descrambling
 * produces the native browser bytes. Consequently this adapter performs
 * an optional copy of the original custom bootstrap's GD setup, but NOT
 * its rescrambling. This separate hardware diagnostic restores the full
 * original GD setup and records bounded-init results for checkpointing.
 *
 * Derived from original IP.BIN offsets 0x61a0..0x6298, except that all
 * incoming general registers and PR are saved/restored. R0 alone is used
 * for the final jump; original offset 0x0c immediately replaces R0.
 */
    .section .text
    .align 2
    .global _shim_start
    .extern _vmu_checkpoint
    .ifndef VMU_FULL_GD_SETUP
    .set VMU_FULL_GD_SETUP,1
    .endif
_shim_start:
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
    sts.l pr,@-r15
    mov.l .Ldiagnostic_addr,r13
    mov.l .Lrom_base,r0
    or r0,r13
    mov #1,r0
    mov.l r0,@r13
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #1,r4

    .if VMU_FULL_GD_SETUP
    /* Original 8c00e1a4..8c00e1b4: Holly GD-ROM access plus ROM reads. */
    mov.l .Lholly_addr,r1
    mov.l .Lholly_value,r0
    mov.l r0,@r1
    mov.l .Lrom_base,r0
    mov #8,r2
    shll16 r2
.Lrom_read:
    dt r2
    bf/s .Lrom_read
    mov.l @r0+,r1
    .global _shim_after_rom
_shim_after_rom:
    mov #2,r0
    mov.l r0,@r13

    /* Original BIOS-shadow patch pairs, only applied when matched. */
    mova .Lold1,r0
    mov r0,r4
    mova .Lnew1,r0
    bsr .Lpatch_bios
    mov r0,r5
    mov.l r0,@(16,r13)
    mov #3,r0
    mov.l r0,@r13
    mova .Lold2,r0
    mov r0,r4
    mova .Lnew2,r0
    bsr .Lpatch_bios
    mov r0,r5
    mov.l r0,@(20,r13)
    mov #4,r0
    mov.l r0,@r13

    /* Original gd syscall 3, then request INIT (command 24). */
    bsr .Lgd_call
    mov #3,r7
    mov #24,r4
    mov #0,r5
    bsr .Lgd_call
    mov #0,r7
    mov r0,r14
    mov.l r0,@(8,r13)
    mov.l r0,@(12,r13)
    cmp/pz r0
    bf .Lrequest_failed
    mov #5,r0
    mov.l r0,@r13
    mov.l .Lpoll_budget,r12
.Lgd_wait:
    mov.l r12,@(24,r13)
    bsr .Lgd_call
    mov #2,r7
    mov r14,r4
    mova .Lgd_status,r0
    mov r0,r5
    bsr .Lgd_call
    mov #1,r7
    mov.l r0,@(8,r13)
    cmp/eq #2,r0
    bt .Lgd_complete
    cmp/eq #1,r0
    bf .Lstatus_failed
    dt r12
    bf .Lgd_wait
    mov #6,r0
    bra .Linit_failed
    nop
.Lrequest_failed:
    mov #1,r0
    bra .Linit_failed
    nop
.Lstatus_failed:
    cmp/eq #0,r0
    bt .Lstatus_missing
    cmp/eq #3,r0
    bt .Lstatus_aborted
    cmp/pz r0
    bf .Lstatus_error
    mov #5,r0
    bra .Linit_failed
    nop
.Lstatus_missing:
    mov #2,r0
    bra .Linit_failed
    nop
.Lstatus_aborted:
    mov #3,r0
    bra .Linit_failed
    nop
.Lstatus_error:
    mov #4,r0
.Linit_failed:
    mov.l r0,@(4,r13)
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #5,r4
    .global _shim_failure
_shim_failure:
    bra _shim_failure
    nop
.Lgd_complete:
    .global _shim_after_gd_init
_shim_after_gd_init:
    mov #6,r0
    mov.l r0,@r13
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #2,r4
    .endif

    /*
     * Keep the runtime wrapper outside browser BSS. Browser startup clears
     * 8c2bd900..8c3f6dc0, which includes this appended entry adapter.
     * Use a consumed part of the MR image source at ac00b900. The BOING
     * bootstrap has finished drawing that image and transferred control
     * before this entry runs; this source data is no longer needed.
     * The browser clears c000..f400, so keep the wrapper below c000.
     * The original CD bootstrap bytes remain unchanged. Do not use the
     * BIOS-shadow/default exception-handler RAM at 0000..7fff.
     */
    mov.l .Lgd_vector,r1
    mov.l @r1,r2
    mova .Loriginal_gd,r0
    mov.l r2,@r0
    mova .Lwrapper_start,r0
    mov r0,r4
    mova .Lwrapper_end,r0
    mov r0,r5
    mov.l .Lresident_addr,r6
    mov r6,r7
.Lcopy_wrapper:
    mov.l @r4+,r0
    mov.l r0,@r6
    add #4,r6
    cmp/eq r4,r5
    bf .Lcopy_wrapper
    mov.l r7,@r1
    /* Update the cached alias too, avoiding an old vector cache line. */
    mov.l .Lgd_vector_cached,r1
    mov.l r7,@r1
    mov #7,r0
    mov.l r0,@r13
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #3,r4
    .global _shim_after_hook
_shim_after_hook:
    mov #8,r0
    mov.l r0,@r13
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #4,r4

    /* No call to original 8c00e35e: normal mkdcdisc already handles it. */
    lds.l @r15+,pr
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
    mov.l @r15+,r0
    mov.l .Lnative_entry,r0
    jmp @r0
    nop

    /*
     * Optional CCR-to-CRT transition. The native file offset 0x2c is
     * normally 8c1dc360; point only that literal to this symbol's P2 alias
     * to use the thunk. Eight NOPs precede any cached data or code access,
     * satisfying SH7750 CCR sequencing even when caches are enabled.
     * Blue checkpoint 6 proves entry here after the native CCR prologue.
     * It does not by itself prove execution of the native CRT entry.
     */
    .align 2
    .global _shim_cache_entry
_shim_cache_entry:
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    mov.l .Lcrt_entry,r0
    mov.l r0,@-r15
    mov.l r4,@-r15
    sts.l pr,@-r15
    mov.l .Lcheckpoint_addr,r0
    jsr @r0
    mov #6,r4
    lds.l @r15+,pr
    mov.l @r15+,r4
    mov.l @r15+,r0
    jmp @r0
    nop

    /* Original 8c00e206..8c00e210, no PR modification. */
.Lgd_call:
    mov.l .Lgd_vector,r0
    mov.l .Lrom_base,r1
    mov.l @r0,r0
    or r1,r0
    jmp @r0
    mov #0,r6

    /* Exact original 10-byte search/replace algorithm. */
.Lpatch_bios:
    mov.l .Lbios_base,r6
    mov.l .Lbios_stop,r7
    dt r6
.Lscan:
    add #1,r6
    cmp/eq r6,r7
    bt/s .Lnot_found
    mov #0,r0
.Lcompare:
    mov.b @(r0,r6),r1
    mov.b @(r0,r4),r2
    add #1,r0
    cmp/eq r1,r2
    bf/s .Lscan
    cmp/eq #10,r0
    bf .Lcompare
.Lreplace:
    mov.b @r5+,r1
    mov.b r1,@r6
    dt r0
    bf/s .Lreplace
    add #1,r6
    mov #1,r0
.Lnot_found:
    rts
    nop

    .align 2
.Lholly_addr:   .long 0xa05f74e4
.Lholly_value:  .long 0x001fffff
.Lrom_base:     .long 0xa0000000
.Lgd_vector:    .long 0xac0000bc
.Lgd_vector_cached: .long 0x8c0000bc
.Lbios_base:    .long 0xac000000
.Lbios_stop:    .long 0xac003ff9
.Lnative_entry: .long 0xac01000c
.Lcrt_entry:    .long 0x8c1dc360
.Lresident_addr: .long 0xac00b900
.Lpoll_budget:   .long 0x00100000
.Ldiagnostic_addr: .long _shim_diagnostic_state
.Lcheckpoint_addr: .long _vmu_checkpoint

    .align 2
.Lold1:
    .byte 0x00,0x0e,0xa0,0x00,0xa4,0x00,0x00,0x24,0x00,0x08
    .byte 0x09,0x00
.Lnew1:
    .byte 0x00,0x0e,0xa0,0x00,0xa4,0x00,0x00,0x28,0x00,0x08
    .byte 0x09,0x00
.Lold2:
    .byte 0x7c,0x67,0x20,0x35,0x01,0x8d,0x0f,0xe3,0x73,0x65
    .byte 0x09,0x00
.Lnew2:
    .byte 0x73,0x60,0x0f,0xc9,0x80,0xcb,0x0f,0xe3,0x03,0x65
    .byte 0x09,0x00
.Lgd_status:
    .long 0,0,0,0

    /*
     * Position-independent GD-ROM syscall wrapper. Passthrough all calls
     * except successful GDROM_CHECK_DRIVE (r6=0,r7=4). Only convert valid
     * loaded CD-ROM/CD-XA/CD-i types, preserving status and low type bits.
     * Error, busy, lid-open, no-disc, retry, fatal and audio-only states
     * remain untouched. R8/R9 and PR follow the normal callee-save ABI.
     */
    .align 2
.Lwrapper_start:
    mov r6,r0
    cmp/eq #0,r0
    bf .Lpass_through
    mov r7,r0
    cmp/eq #4,r0
    bf .Lpass_through
    tst r4,r4
    bt .Lpass_through
    mov.l r8,@-r15
    mov.l r9,@-r15
    sts.l pr,@-r15
    mov r4,r8
    mov.l .Loriginal_gd,r0
    jsr @r0
    nop
    mov r0,r9
    tst r0,r0
    bf .Ldrive_done
    mov.l @r8,r0
    cmp/pl r0
    bf .Ldrive_done
    mov #5,r1
    cmp/hi r1,r0
    bt .Ldrive_done
    mov.l @(4,r8),r0
    and #240,r0
    cmp/eq #16,r0
    bt .Lforce_gd
    cmp/eq #32,r0
    bt .Lforce_gd
    cmp/eq #48,r0
    bf .Ldrive_done
.Lforce_gd:
    mov.l @(4,r8),r0
    and #15,r0
    or #128,r0
    mov.l r0,@(4,r8)
.Ldrive_done:
    mov r9,r0
    lds.l @r15+,pr
    mov.l @r15+,r9
    rts
    mov.l @r15+,r8
.Lpass_through:
    mov.l .Loriginal_gd,r0
    jmp @r0
    nop
    .align 2
.Loriginal_gd:
    .long 0
.Lwrapper_end:
    .align 2
    .global _shim_diagnostic_state
_shim_diagnostic_state:
    /* stage, reason, last_return, request_id, patch1, patch2, polls_left */
    .long 0,0,0,0,0,0,0
