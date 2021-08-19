#!/bin/sh
riscv64-unknown-elf-as -march=rv32imac game.asm
riscv64-unknown-elf-objcopy -O binary a.out game.o
xxd game.o
