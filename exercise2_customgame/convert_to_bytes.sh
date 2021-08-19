#!/bin/sh
riscv64-unknown-elf-gcc -Os -nostdlib -nostartfiles -Tuser.lds -ffreestanding $1 -o userprog.o
ASM=$(riscv64-unknown-elf-objdump --disassemble=main userprog.o | grep -P ":\t" | cut -f2 | tr -d ' ')

BYTES=""
for a in $ASM;
do
    BYTES+=$(echo -n "$a" | tac -rs ..);
done;
echo -n $BYTES | xxd -r -p
