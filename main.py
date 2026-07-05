"""
Copyright (c) 2022 Gary Sims

07/21/2024
Expanded by Casey Clewell to support two 8x8 matrixes, one for H,Min,S, and one for Y, Mth, D.
Also added support for a toggle button to select between the three clock style types (binary,
bcd, length), and the ability to save the last selection persistently.

MIT License
SPDX-License-Identifier: MIT
"""

import max7219
from time import sleep
from machine import RTC
import network
import time
from machine import Pin, RTC, SPI
import urequests
import ntptime


clock_style = 1 # 1 = 3 col, 2 = 6 col BDC, 3 = length style
clock_style_update_pending = False
last_button_val = 0
light_sleep = False
wake_time = 30 # seconds
wake_counter = 0


def binary_at(disp, b, x):
    y = 7
    while y > 1:
        bit = b & 0x01
        if bit == 1:
            disp.pixel(x, y, 1)
        y = y - 1
        b = b >> 1

def bcd_at(disp, b, x):
    d1 = b // 10
    d2 = b % 10
    #print(b, d1, d2)
    binary_at(display, d1, x)
    binary_at(display, d2, x+1)

def len_at(disp, b, x):
    d1 = b // 10
    d2 = b % 10

    disp.vline(x, 8-d1, d1, 1)
    if d2==9:
        disp.pixel(x,0,1)
    disp.vline(x+1, 8-d2, d2, 1)

def sync_time_with_worldtimeapi_org(rtc, blocking=True):
    # setup network connection
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # Enter your WIFI SSID and PW here
    wlan.connect('casvic', 'SfGvHlM2010Z98V69C68')

    # Wait for connection with timeout
    max_wait = 20
    while max_wait > 0 and not wlan.isconnected():
        status = wlan.status()
        print("Waiting for connection... status =", status)
        if status < 0: # Connection failed or config error
            break
        time.sleep(1)
        max_wait -= 1

    if not wlan.isconnected():
        print("Wi-Fi connection failed! Status:", wlan.status())
        print("Please verify your Wi-Fi SSID and password in main.py.")
        return

    print("Wi-Fi connected! IP config:", wlan.ifconfig())


    # 1. Fetch timezone offset from ip-api.com (uses plain HTTP, no SSL)
    offset = -7 * 3600  # Default fallback timezone offset (e.g. UTC-7)
    try:
        print("Fetching timezone offset from ip-api.com...")
        response = urequests.get("http://ip-api.com/json/?fields=status,offset")
        data = response.json()
        if data.get("status") == "success":
            offset = data.get("offset", offset)
            print("Successfully detected timezone offset:", offset, "seconds")
        else:
            print("Failed to auto-detect timezone offset, using fallback:", offset)
        response.close()
    except Exception as e:
        print("Could not auto-detect timezone offset:", e, "using fallback:", offset)

    # 2. Sync UTC time using NTP
    ntp_synced = False
    while True:
        try:
            print("Synchronizing time via NTP...")
            ntptime.settime()
            ntp_synced = True
            break
        except Exception as e:
            print("NTP sync failed:", e)
            if blocking:
                time.sleep(5)
                continue
            else:
                break

    if ntp_synced:
        # Calculate local time
        local_time = time.time() + offset
        tm = time.localtime(local_time)
        rtc.datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
        print("Time synced successfully! Current local time:", time.localtime())
    else:
        print("NTP synchronization failed, RTC not updated.")

    # shutdown network connection.
    wlan.disconnect
    wlan.active(False)

def button_transition_detected(pin):
    global last_button_val
    #debounce logic. Make sure the button value change is real
    current_button_val = pin.value()
    counter_ms = 0;
    while (counter_ms < 20 and pin.value() == current_button_val):
        print("running button val = " + str(pin.value()) + " current_button_val = " + str(current_button_val))
        counter_ms += 1
        time.sleep_ms(1)
        
    if counter_ms >= 20:
        # We only trigger an update when the button value
        # transitions from 0 to 1
        if current_button_val == 1:
            if last_button_val == 0:
                last_button_val = 1
                return True
        else:
            if last_button_val == 1:
                last_button_val = 0
    return False
    
# Interrupt handler for the button press
def button_press_handler(pin):
    global clock_style, clock_style_update_pending, last_button_val, light_sleep, wake_counter, skip_next
    if not light_sleep:
        # only take action if an update is not pending
        if not clock_style_update_pending:                
            if button_transition_detected(pin):
                # update the clock style
                clock_style += 1
                if clock_style > 3:
                    clock_style = 1
                clock_style_update_pending = True
                print('clock style update pending')
    else:
        light_sleep = False
        wake_counter = 0
        print("Awake")
     
    
led = Pin("LED", Pin.OUT)
led.off()

#Matrix init (8x8 * 2)
spi = SPI(0,sck=Pin(2),mosi=Pin(3))
cs = Pin(5, Pin.OUT)
display = max7219.Matrix8x8(spi, cs, 2)
display.brightness(0)
display.fill(0)
display.show()

# led.on()

machine.freq(70000000)
print('machine.freq = ' + str(machine.freq()))

rtc = RTC()
sync_time_with_worldtimeapi_org(rtc)

#init clock style
try:
    conf_file = open("bin_clock.ini", 'r')
    file_content = conf_file.read()
    #the only thing in the file is the last selected clock style
    clock_style = int(file_content)
    conf_file.close()
except:
    conf_file = open("bin_clock.ini", 'w')
    conf_file.write(str(clock_style))
    conf_file.close()
print("clock_style = " + str(clock_style))

               
force_sync_counter = 0
# set up button interrupt handlers
button1 = Pin(16, Pin.IN, Pin.PULL_UP)
button1.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,handler=button_press_handler)

# led_count = 0
# while led_count < 4:
#     led.toggle()
#     sleep(1)
#     led_count = led_count + 1

while True:
    if not light_sleep:
        # print("button1.value() = " + str(button1.value()))
        # check for button activity
        if clock_style_update_pending:
            try:
                # save the new clock style selection to file
                conf_file = open("bin_clock.ini", 'w')
                conf_file.write(str(clock_style))
                conf_file.close()
                print("clock_style now equals " + str(clock_style) + " and has been saved to file")
            except:
                print("Error saving clock_style to file")
            clock_style_update_pending = False
           
        led.toggle()
        
        # get the current time from the real time clock
        Y, MTH, D, W, H, M, S, SS = rtc.datetime()
        # subtract 2000 from the year to get a 2 digit year
        Y = Y - 2000
        #print(Y, MTH, D, H, M, S)

        display.fill(0)

        if clock_style == 1:
            binary_at(display, H, 9)
            binary_at(display, M, 12)
            binary_at(display, S, 15)
            binary_at(display, D, 1)
            binary_at(display, MTH, 4)
            binary_at(display, Y, 7)
        elif clock_style == 2:
            bcd_at(display, H, 8)
            bcd_at(display, M, 11)
            bcd_at(display, S, 14)
            bcd_at(display, D, 0)
            bcd_at(display, MTH, 3)
            bcd_at(display, Y, 6)
        else:
            len_at(display, H, 8)
            len_at(display, M, 11)
            len_at(display, S, 14)
            len_at(display, D, 0)
            len_at(display, MTH, 3)
            len_at(display, Y, 6)
        
        display.show()
        
        if force_sync_counter > 85000: # A little less than a day
            force_sync_counter = 0
            sync_time_with_worldtimeapi_org(rtc, blocking=False)
            
        force_sync_counter = force_sync_counter + 1
        wake_counter = wake_counter + 1
        if wake_counter >= wake_time:
            # go into light sleep mode here
            display.fill(0)
            display.show()
            led.off()
            light_sleep = True
            print("Sleep")
    sleep(1)
    
