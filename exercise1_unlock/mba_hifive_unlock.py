#!/usr/bin/env python3
try:
    import serial
except ModuleNotFoundError:
    print("Python is missing the serial library")
    quit()
try:
    import re
except ModuleNotFoundError:
    print("Python is missing the regular expression library")
    quit()
try:
    import time
except ModuleNotFoundError:
    print("Python is missing the time library")
    quit()
try:
    import os
except ModuleNotFoundError:
    print("Python is missing the os library")
    quit()
try:
    import sys
except ModuleNotFoundError:
    print("Python is missing the sys library")
    quit()
try:
    import getopt
except ModuleNotFoundError:
    print("Python is missing the getopt library")
    quit()
    
target_device = 'FE310'
BAUDRATE = 115200
    
def reset_board_pylink(target_device):
    try:
        import pylink
    except ModuleNotFoundError:
        print("Python is missing the pylink library, try pip install pylink-square")
        quit()
    jlink = pylink.JLink()
    jlink.open()
    jlink.connect(target_device)
    jlink.reset(halt=False)
    jlink.close()
    
def reset_board_shell(target_device):
    shell_command = "echo -en '\\rnh\\nrnh\\nexit\\n' | JLinkExe -device fe310 -If JTAG -speed 4000 -Autoconnect 1 > /dev/null"
    ret = os.system(shell_command)
    print('Reset via shell returned: '+(lambda x: 'success' if (x==0) else 'failed')(ret))
    return

def obtain_mac(serial_device):
    print('Obtaining MAC of ESP32')
    ser = serial.Serial(serial_device, BAUDRATE)
    while True:
        try:
            line = ser.readline().decode('utf-8')
            mac_matcher = re.compile('wifi: mode : sta \(([^)]+)\)')
            match = re.search(mac_matcher,line)
            if match:
                return match.group(1)
        except Exception as e: 
            print(e)
            break

def send_secret(serial_device, secret):
    ser = serial.Serial(serial_device, BAUDRATE)
    ser.flushInput()
    #Resetting buffer
    ser.write(bytes('\n', 'utf-8'))
    #Sending secret
    ser.write(bytes(secret, 'utf-8'))
    return ser
    

def is_firmware_unlocked(ser):
    expected_answer = 'Password correct.'
    while True:
        try:
            ser_line = ser.readline().decode('utf-8')
            if expected_answer in ser_line:
                return True
        except Exception as e: 
            #print(e)
            print("Keyboard Interrupt")
            break

def main(argv):
    try:
        opts, args = getopt.getopt(argv,"hr:",["reset="])
    except getopt.GetoptError:
        print('mba_hifive_unlock.py -r <reset-type>')
        print('reset-type: pylink --> [Default] needs installed pylink lib (pip install pylink-square)')
        print('reset-type: shell ---> needs installed JLinkExe tool')
        quit()
    reset = 'pylink'
    for opt, arg in opts:
        if opt == '-h':
            print('mba_hifive_unlock.py -r <reset-type>')
            print('reset-type: pylink --> [Default] needs installed pylink lib (pip install pylink-square)')
            print('reset-type: shell ---> needs installed JLinkExe tool')
            quit()
        elif opt in ("-r", "--reset"):
            reset = arg
    print('Reset-type set to ' + reset)
    if reset == 'shell':
        reset_board_shell(target_device)
    else:
        reset_board_pylink(target_device)
    mac = obtain_mac('/dev/ttyACM1')
    if not mac:
        print("No MAC found, aborting")
        quit()
    print(mac)
    secret = "__SecLab__"+mac +"\r\n"
    time.sleep(3)
    ser = send_secret('/dev/ttyACM0', secret)
    if is_firmware_unlocked(ser):
        print('Successfully unlocked firmware')
    else:
        print('Something went wrong :O')

if __name__ == '__main__':
    main(sys.argv[1:])
