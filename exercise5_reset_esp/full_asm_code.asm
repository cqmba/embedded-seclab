#extend_rw
xor     a0,a0,a0
ori     a0,a0,0x5
lui     a1,0x8001
addi    a1,a1,0x700
ecall
addi    a0,a0,1
lui     a1,0x80003
addi    a1,a1,0x700
addi    a1,a1,0x208
ecall

#exit_syscall
xor     a0,a0,a0
ori     a0,a0,0x1


#second game code
lui     a2,0x8000
lui     a1,0x8001
addi    a1,a1,0x700
lw      a3,0x0(a1)
sw      a3,0x0(a2)
lui     a2,0x8001
addi    a2,a2,0x20
ecall
addi    x0,x0,0
lui     a0,0x20011
addi    a0,a0,0xa0
lui     a1,0x20010
addi    a1,a1,0x194
jalr    ra,a1,0x0
lui     a2,0x8000
lui     a1,0x8001
addi    a1,a1,0x704
lw      a3,0x0(a1)
sw      a3,0x0(a2)
xor     a0,a0,a0
addi    a0,a0,0x1    
c.jr    a2
c.nop

jump_at_handler_to_my_code:
c.nop
c.jr    a2

