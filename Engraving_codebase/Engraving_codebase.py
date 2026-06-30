### Grbl Sender written by Roger Lu0 18-11-2025
        # $$ (view Grbl settings)
        # $# (view # parameters)
        # $G (view parser state)
        # $I (view build info)
        # $N (view startup blocks)
        # $x=value (save Grbl setting)
        # $Nx=line (save startup block)
        # $C (check gcode mode)
        # $X (kill alarm lock)
        # $H (run homing cycle)
        # ~ (cycle start)
        # ! (feed hold)
        # ? (current status)
        # ctrl-x (reset Grbl)

# To dos
# - include alarm mode, check for that, when in alarm mode the arduino freezes and you cannot run 
# the command, not even home

# - log time for everything, so that intelligent time predictions can be made

# - make file transfer work with gcode writing

# - make a visual interface to preview the generated Gcode (can even load in am image of a 
# engraving plate for dimensional reference)

# - make a string and generator editor that allows for quick additions to the plate by then 
# subsequently concatinating the files

# - add a verbose switch


import serial
import time
import glob
from threading import Event 
import math
from datetime import datetime, timedelta
import subprocess
import os
import re
from dataclasses import dataclass, asdict, is_dataclass
import json
import numpy as np 
import matplotlib.pyplot as plt
import math
# from pynput import keyboard


BAUD_RATE = 115200
# def jog(ser,increment=1):
#     ser.write(b"")

@dataclass
class config: 
    notes: str = "Configuration save file for current engraving session"
    mapping_work: tuple = (193.001, 172.801, 28.521)
    mapping_lath: tuple = (198.1, 179.801, 22.581)
    islath: bool = False
    wPos_home: tuple = (0, 125, 15)
    finish_wPos: tuple = (0, 125, 15)
    beddim: tuple = (120, 80)
    year: str = str(datetime.now().year)[2:]
    plate_counter: tuple = (0, 0, 0, 0)  # NSW, QLD, VIC_Heavy, VIC_Light
    avg_vars: tuple = (0, 0, 0)  # y, x, u
    avg_n: int = 0  # number of samples for time estimate
    sum_vars: tuple = (0, 0, 0, 0, 0, 0, 0)  # xi^2, xi, xiui, xiyi, ui, ui^2, uiyi






def remove_comments(string): 
    # for a given line of gcode, removes the comments by taking the previous characters
    if (string.find(';') == -1):
        return string
    else: 
        return string[:string.index(';')]


def remove_eol_chars(string): 
    # get rid of /n
    return string.strip()
    

def send_wakeup(ser=None, port="/dev/ttyUSB0",baud=115200): 
    # make sure nothing else is running
    if ser: 
        ser.write(b"\r\n\r\n")
        time.sleep(1)
        ser.reset_input_buffer()
        return ser
    else: 
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(1)
        ser.write(b"\r\n\r\n")
        ser.reset_input_buffer()
        return ser


def verify_wPos(ser, mapping=(193.001, 172.801, 28.521), verbose=False): 
    # wPos to mPos mapping
    # mapping = wPos - mPos 
    ser.reset_input_buffer()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()

    if verbose: 
        print(string)

    MPos = string[string.index("M")+5:string.index("W")-1]
    MPos = tuple(float(i) for i in MPos.split(","))

    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))

    cur_map = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
    
    if verbose: 
        print("string response read as: ", string)
        print("Machine cordinate: ", MPos)
        print("Work cordinates: ", WPos)

    if (abs(cur_map[0] - mapping[0]) >= 0.1) or (abs(cur_map[1] - mapping[1]) >= 0.1) or (abs(cur_map[2] - mapping[2]) >= 0.1): 
        if verbose: 
            print("Machine Position Inaccurate..")
            print(f"difference : {abs(cur_map[0] - mapping[0])}, {abs(cur_map[1] - mapping[1])}, {abs(cur_map[2] - mapping[2])}")
            print("Recalibrating...")

        homeNcalibrate(ser, mapping=mapping)

    else: 
        if verbose: 
            print("Machine Position Accurate. ")
        return ser
    
    return ser


def homeNcalibrate(ser, mapping=(193.001, 172.801, 28.521), wPos=(0, 125, 25), verbose=False):
    if verbose: 
        print("homing")
    ser.reset_input_buffer()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()
    ser.reset_input_buffer()
    ser.write(b"$H\n")
     # NEED /n to execute the command

    wait_for_movement_completion(ser,"$H\n", verbose=verbose)
    mPos = (wPos[0] - mapping[0], wPos[1] - mapping[1], wPos[2] - mapping[2])
    home_cmd = f"G53 X{mPos[0]:.3f} Y{mPos[1]:.3f} Z{mPos[2]:.3f}\n"
    ser.write(str.encode(home_cmd))
    wait_for_idle(ser)
    time.sleep(2)
    work_cmd = f"G92 X{wPos[0]:.3f} Y{wPos[1]:.3f} Z{wPos[2]:.3f}\n"
    ser.write(str.encode(work_cmd))
    wait_for_idle(ser)
    return ser


def wait_for_movement_completion(ser, clean_cmd_line, verbose=False): 
    # Event().wait(1)
    ser.reset_input_buffer()
    if clean_cmd_line not in ("$X", "$$"): 
        cmd_out = ser.readline().strip().decode()
        if verbose: 
            print(f"immediete out : {cmd_out}") # flag immediete out 1 
        while cmd_out != "ok": 
            # print("inside loop")
            if "alarm" in cmd_out.lower():
                print("Machine in Alarm state!")
                if verbose: 
                    print("cmd out:", cmd_out)
                pass

            
            if "error" in cmd_out:
                # print the error out
                print(f"ERROR sending {clean_cmd_line}: {cmd_out}")
            elif "hard" in cmd_out.lower(): 
                print("Hard Limit reached! Manually move spindle away from limit switches and restart.")
                break
            cmd_out = ser.readline().strip().decode()
            if verbose:
                print(cmd_out)
        
        return None

def wait_for_idle(ser): 
    while True:
        ser.write(b"?")
        time.sleep(0.1)
        status = ser.readline().decode()
        if "<Idle" in status:
            return

def write_gcode(ser, g_code_path, spindle_travel=None, spindle_stops=None, verbose=False):
    start_time = time.perf_counter()
    file = open(g_code_path,'r')
    if verbose: 
        print("file opened")
    # send wakeup to ser
    ser.write(b'\r\n\r\n') 
    time.sleep(1)
    # if verbose: 
    #     print("going to zero X and Y in work cordinates. ")
    # ser.write(str.encode("G0 X0 Y0 Z10" + "\n"))
    # time.sleep(10)
    # if verbose: 
    #     print("going to approximate top right corner of plate in work cordinates.0")
    # ser.write(str.encode("G0 X90 Y49 Z10" + "\n"))

    # check work cordinate mapping
    # verify_wPos(ser, mapping)
    for line in file: 
        cleaned_line = remove_eol_chars(remove_comments(line))

        if cleaned_line:  # ensure that it is not None
            # print("sending G-code: " + str(cleaned_line))

            ser.write(str.encode(cleaned_line + "\n"))
            

            wait_for_movement_completion(ser, cleaned_line)

    end_time = time.perf_counter()
    
    print_time = abs(start_time - end_time) # seconds

    
    # update counters
    config_path = "/home/pi/Documents/Engraving_codebase/script_config.json"
    with open(config_path, "r") as f:
        config_dict = json.load(f)
        sesh_config = config(**config_dict)  # unpacking dictionary to config dataclass

    print("Config pre mod: ", sesh_config)
    if (spindle_travel is not None) and (spindle_stops is not None): 
        time_avg_old = sesh_config.avg_vars[0]
        travel_avg_old = sesh_config.avg_vars[1]
        stop_avg_old = sesh_config.avg_vars[2]
        n = sesh_config.avg_n

        time_avg_new = time_avg_old*(n/(n+1)) + print_time/(n+1)
        travel_avg_new = travel_avg_old*(n/(n+1)) + spindle_travel/(n+1)
        stop_avg_new = stop_avg_old*(n/(n+1)) + spindle_stops/(n+1)

        # summation terms
        xi2 = sesh_config.sum_vars[0] + spindle_travel**2
        xi = sesh_config.sum_vars[1] + spindle_travel 
        xiui = sesh_config.sum_vars[2] + spindle_travel*spindle_stops
        xiyi = sesh_config.sum_vars[3] + spindle_travel*print_time
        ui = sesh_config.sum_vars[4] + spindle_stops
        ui2 = sesh_config.sum_vars[5] + spindle_stops**2
        uiyi = sesh_config.sum_vars[6] + spindle_stops*print_time

        sesh_config.avg_n = n + 1

        sesh_config.avg_vars = (time_avg_new, travel_avg_new, stop_avg_new) # tuple
        sesh_config.sum_vars = (xi2, xi, xiui, xiyi, ui, ui2, uiyi)
        print("CONFIG POST MOD: ", sesh_config) # FLAG
        with open(config_path, "w") as f: 
            # convert config dataclass to dictionary 
            json.dump(asdict(sesh_config), f, indent=4)



    print("====End====")
    return print_time


def scan_grbl_port(baud=115200):

    ports = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") # pretty much searches for these port by typing it in the bash

    for port in ports: 
        try: 
            ser = serial.Serial(port, baud, timeout=1)
            time.sleep(2)

            ser.write(b'\r\n\r\n') # ctr-x
            time.sleep(1)
            
            ser.write(b"\x18")# ctr-x
            time.sleep(1)

            response = ser.read(100).decode()  # .read(100) reads 100 bytes, returned as raw byte objects, decode converts to python string 

            ser.close()
            
            if 'Grbl' in response:
                return port
        except Exception:
            pass

    return None


def calibrate_spoilboard(depth, bed_dim=(125, 80)):
    """
    Alternating cross-hatch spoilboard surfacing with:
      - 1 plunge per layer
      - serpentine raster (no safe-Z between every pass)
      - even layers: vertical (constant X, sweep Y)
      - odd  layers: horizontal (constant Y, sweep X)
    """
    stepover      = 1.8
    board_length  = bed_dim[0]   # X (mm)
    board_width   = bed_dim[1]   # Y (mm)
    margin        = 0.0
    safe_z        = 5.0
    skim_step_z   = -0.10        # mm per layer (negative = down)
    plunge_feed   = 120
    cut_feed      = 200
    spindle_rpm   = 12000

    # Number of skim layers to reach requested total depth
    surfaces = math.ceil(abs(depth / skim_step_z))
    x0, x1 = margin, board_length - margin
    y0, y1 = margin, board_width  - margin

    lines = [
        f"(3018 spoilboard surfacing - {board_length} x {board_width} mm, cross-hatch, stepover {stepover} mm, {skim_step_z:.2f} mm/layer)",
        "G21", "G90", "G17",
        f"M3 S{int(spindle_rpm)}",
        f"G0 Z{safe_z:.2f}",
        f"G0 X{x0:.2f} Y{y0:.2f}"
    ]

    for j in range(surfaces):
        z = skim_step_z * (j + 1)
        vertical = (j % 2 == 0)

        if vertical:
            # Vertical raster: step in X, sweep Y
            n = math.ceil((x1 - x0) / stepover) + 1

            # Rapid to first start point (safe), plunge once, then cut continuously
            lines += [
                f"(Layer {j+1}/{surfaces}: vertical)",
                f"G0 Z{safe_z:.2f}",
                f"G0 X{x0:.2f} Y{y0:.2f}",
                f"G1 Z{z:.2f} F{plunge_feed}",
            ]

            for i in range(n):
                x = min(x0 + i * stepover, x1)
                if i % 2 == 0:
                    # go up in Y
                    lines += [
                        f"G1 X{x:.2f} Y{y1:.2f} F{cut_feed}",
                    ]
                else:
                    # go down in Y
                    lines += [
                        f"G1 X{x:.2f} Y{y0:.2f} F{cut_feed}",
                    ]

                # move over to next stripe at same Z (except after last)
                if i != n - 1:
                    x_next = min(x0 + (i + 1) * stepover, x1)
                    y_hold = y1 if (i % 2 == 0) else y0
                    lines += [f"G1 X{x_next:.2f} Y{y_hold:.2f} F{cut_feed}"]

            # Retract once at end of layer
            lines += [f"G0 Z{safe_z:.2f}"]

        else:
            # Horizontal raster: step in Y, sweep X
            n = math.ceil((y1 - y0) / stepover) + 1

            lines += [
                f"(Layer {j+1}/{surfaces}: horizontal)",
                f"G0 Z{safe_z:.2f}",
                f"G0 X{x0:.2f} Y{y0:.2f}",
                f"G1 Z{z:.2f} F{plunge_feed}",
            ]

            for i in range(n):
                y = min(y0 + i * stepover, y1)
                if i % 2 == 0:
                    # go right in X
                    lines += [
                        f"G1 X{x1:.2f} Y{y:.2f} F{cut_feed}",
                    ]
                else:
                    # go left in X
                    lines += [
                        f"G1 X{x0:.2f} Y{y:.2f} F{cut_feed}",
                    ]

                if i != n - 1:
                    y_next = min(y0 + (i + 1) * stepover, y1)
                    x_hold = x1 if (i % 2 == 0) else x0
                    lines += [f"G1 X{x_hold:.2f} Y{y_next:.2f} F{cut_feed}"]

            lines += [f"G0 Z{safe_z:.2f}"]

    lines.extend([
        "G0 X0 Y0",
        "M5",
        "M30"
    ])

    # log the lathing gcode
    gcode = "\n".join(lines)
    log_file_path = f"log_dump/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{depth}mm_{board_length}_x_{board_width}.nc"
    with open(log_file_path, "w") as f:
        f.write(gcode)

    # Placeholder estimate like before
    pass_t = timedelta(minutes=32, seconds=11)
    cal_time = pass_t * surfaces

    print(f"Calibration G-code Generated: {log_file_path}")
    print(f"Estimated Time: {cal_time}")
    return gcode, log_file_path, cal_time


# Source - https://stackoverflow.com/a
# Posted by Flux, modified by community. See post 'Timeline' for change history
# Retrieved 2025-12-08, License - CC BY-SA 4.0
# thank you <3
def getch():
    import sys, termios, tty

    fd = sys.stdin.fileno()
    orig = termios.tcgetattr(fd)

    try:
        tty.setcbreak(fd)  # or tty.setraw(fd) if you prefer raw mode's behavior.
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSAFLUSH, orig)


def jog(ser, mapping):
    # inputs, serial stringe
    print("----------------------jog mode-----------------------")
    print("use 'wasd-qe' to move the spindle in the xy-z direction, where e is negative in z. ")
    print("use 'n' to exit jog mode. ")
    print("use 'b' to zero xy cordinates")
    print("use 'v' to zero z cordinates")
    print("use 'x' to toggle on spindle")
    print("use 'p' to goto a specific work cordinate")
    print("use 'm' to switch jog speeds: ")
    print("- 0.01 mm ")
    print("- 0.05 mm ")
    print("- 0.1 mm (DEFAULT)")
    print("- 0.2 mm ")
    print("- 0.5 mm ")
    print("- 1 mm ")
    print("- 2 mm ")
    print("- 5 mm ")
    print("- 10 mm ")
    print("- 20 mm ")
    print("- 50 mm ")
    print("\n\n\n\nuse wasd-qe to move the spindle manually:\n")

    spds = [0.01, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50]
    idx = 2
    new_map = mapping
    spdl_id = 0
    while True: 
        try: 
            cur_spd = spds[idx]
            keyboardInput = getch().lower()
            if keyboardInput =='n': 
                break
            elif keyboardInput =='m': 
                idx = idx + 1 if idx < 10 else 0
                cur_spd = spds[idx]
                print(f"Movement Increment: {cur_spd} mm")
            elif keyboardInput == 'w' or keyboardInput == 's':
                cmd = f'G91 Y{cur_spd}\n' if keyboardInput == 'w' else f'G91 Y{-cur_spd}\n'
                ser.write(str.encode(cmd))
                wait_for_movement_completion(ser, cmd)
            elif keyboardInput == "a" or keyboardInput == "d": 
                cmd = f"G91 X{cur_spd}\n" if keyboardInput == "d" else f"G91 X{-cur_spd}\n"
                ser.write(str.encode(cmd))
                wait_for_movement_completion(ser, cmd)
            elif keyboardInput == "q" or keyboardInput == "e": 
                cmd = f"G91 Z{cur_spd}\n" if keyboardInput == "q" else f"G91 Z{-cur_spd}\n" 
                ser.write(str.encode(cmd))
                wait_for_movement_completion(ser, cmd)
            elif keyboardInput == 'b' or keyboardInput == 'v':
                if keyboardInput == "b":
                    ser, new_map = zero_xy(ser)
                    print(f"machine xy position Zeroed! current mapping: {new_map}")
                else:
                    ser, new_map = zero_z(ser)
                    print(f"machine z position zeroed! current mapping: {new_map}")
            elif keyboardInput == "x":
                if spdl_id == 0:  
                    ser.write(b"M3 S12000\n")
                    print("Spindle On!")
                    spdl_id = 1
                else:
                    ser.write(b"M5\n")
                    print("Spindle Off!")
                    spdl_id = 0
            elif keyboardInput == "p": 
                # move to a user input location
                print("the new mapping is", new_map)
                x_pos = input("Enter X position to move to (enter for current): ") # wpos
                y_pos = input("Enter Y position to move to (Enter for current): ")
                z_pos = input("Enter Z position to move to (Enter for current): ")

                x_pos = float(x_pos) if x_pos != "" else ""
                y_pos = float(y_pos) if y_pos != "" else ""
                z_pos = float(z_pos) if z_pos != "" else ""


                if x_pos == "" and y_pos == "":
                    mPos = (0, 0, z_pos - new_map[2]) 
                    cmd = f"G53 Z{mPos[2]:.3f}\n"
                elif x_pos == "" and z_pos == "":
                    mPos = (0, y_pos - new_map[1], 0) 
                    cmd = f"G53 Y{mPos[1]:.3f}\n"
                elif y_pos == "" and z_pos == "":
                    mPos = (x_pos - new_map[0], 0, 0) 
                    cmd = f"G53 X{mPos[0]:.3f}\n"
                elif x_pos == "":
                    mPos = (0, y_pos - new_map[1], z_pos - new_map[2])
                    cmd = f"G53 Y{mPos[1]:.3f} Z{mPos[2]:.3f}\n"
                elif y_pos == "":
                    mPos = (x_pos - new_map[0], 0, z_pos - new_map[2])
                    cmd = f"G53 X{mPos[0]:.3f} Z{mPos[2]:.3f}\n"
                elif z_pos == "":
                    mPos = (x_pos - new_map[0], y_pos - new_map[1], 0)
                    cmd = f"G53 X{mPos[0]:.3f} Y{mPos[1]:.3f}\n"
                else:
                    mPos = (x_pos - new_map[0], y_pos - new_map[1], z_pos - new_map[2]) 
                    cmd = f"G53 X{mPos[0]:.3f} Y{mPos[1]:.3f} Z{mPos[2]:.3f}\n"
                ser.write(str.encode(cmd))
                wait_for_movement_completion(ser, cmd)
                print("Moved to position!")
        except: 
            print("Error in jog command!")
            break
        


            
    return ser, new_map


def jog_web(ser, speed, direction, spindle_on_bool):
    '''
    
    modified jog function for web applications, takes in preconfigured speed and direction and sends serial message to move the spindle

    '''
    try: 
        if direction =='up' or direction == 'down': 
            cmd = f'G91 Y{speed}\n' if direction == 'up' else f'G91 Y{-speed}\n'
            ser.write(str.encode(cmd))
            wait_for_movement_completion(ser, cmd)
        elif direction == 'left' or direction == 'right': 
            cmd = f"G91 X{speed}\n" if direction == "right" else f"G91 X{-speed}\n"
            ser.write(str.encode(cmd))
            wait_for_movement_completion(ser, cmd)
        elif direction == "high" or direction == "low": 
            cmd = f"G91 Z{speed}\n" if direction == "high" else f"G91 Z{-speed}\n" 
            ser.write(str.encode(cmd))
            wait_for_movement_completion(ser, cmd)
        elif direction == 'on': 
            if spindle_on_bool: 
                ser.write(b"M5\n")
                spindle_on_bool = False
            else: 
                ser.write(b"M3 S12000\n")
                spindle_on_bool = True
    except: 
        
        print("Error in jog command!")
            
    return ser, spindle_on_bool

def estimate_time(ser, gcode_path): 
    '''
    
    estimate the time it would take to engrave in ms

    distance travelled & number of stops/adjustments
    
    t = m * dist + k * stops + c

    progressive regression using historical data 

    '''
    # harvest total path distance and number of stops/ adjustments
    with open(gcode_path, "r") as f: 
        lines = f.readlines()
    
    
    ser.reset_output_buffer()
    ser.reset_input_buffer()
    ser.write(b"?")
    string = ser.read_until(b">").decode()
    print(string)
    # Gcode is written in Work Positions only
    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))
    lines = lines[1:]
    
    spindle_stops = 0
    spindle_travel = 0
    curr_pos = WPos
    feed_rate = 400
    for line in lines: 
        if line.startswith("G0"): 
            spindle_stops = spindle_stops + 1

        # find Feedrate
        if line.find("F") != -1:
            feed_rate = float(line[line.find("F")+1:line.find("F")+6])
        # update new point
        if line.find("X") != -1: 
            xStr = line[line.find("X")+1:]

            if xStr.find("F") != -1: 
                if xStr[xStr.find("F") - 1] != " ":
                    xStr = xStr.split("F")
                else: 
                    xStr = [xStr]
            else: 
                xStr = [xStr]
            
            try: 
                x_new = float(xStr[0])
            except ValueError: 
                xStr = xStr[0].split(" ")
                x_new = float(xStr[0])
        else: 
            x_new = curr_pos[0]

        if line.find("Y") != -1: 
            yStr = line[line.find("Y")+1:]

            if yStr.find("F") != -1: 
                if yStr[yStr.find("F") - 1] != " ":
                    yStr = yStr.split("F")
                else: 
                    yStr = [yStr]
            else: 
                yStr = [yStr]
            
            try: 
                y_new = float(yStr[0])
            except ValueError: 
                yStr = yStr[0].split(" ")
                y_new = float(yStr[0])
        else: 
            y_new = curr_pos[1]

        if line.find("Z") != -1: 
            zStr = line[line.find("Z")+1:]

            if zStr.find("F") != -1: 
                if zStr[zStr.find("F") -1] != " ": 
                    zStr = zStr.split("F")
                else: 
                    zStr = [zStr]
            else: 
                zStr = [zStr]

            try: 
                z_new = float(zStr[0])
            except ValueError: 
                zStr = zStr[0].split(" ")
                z_new = float(zStr[0])
        else: 
            z_new = curr_pos[2]

        dist = math.sqrt((x_new - curr_pos[0])**2 + (y_new - curr_pos[1])**2 + (z_new - curr_pos[2])**2)
        spindle_travel = spindle_travel + dist/(feed_rate/60) # feed is mm/min

        curr_pos = (x_new, y_new, z_new)


    # calculate weights of regression based on previously trained data
    # y: expected time 
    # x: spindle travel 
    # u: spindle stops
    # y = c + m1*x + m2*u
    # where c is the bias, m1 & m2 is the weights for both inputs
    config_path = "/home/pi/Documents/Engraving_codebase/script_config.json"
    with open(config_path, "r") as f:
        config_dict = json.load(f)
        sesh_config = config(**config_dict)  # unpacking dictionary to config dataclass
    f.close()
    # load in variables
    y_bar = sesh_config.avg_vars[0]
    x_bar = sesh_config.avg_vars[1]
    u_bar = sesh_config.avg_vars[2]

    xi2 = sesh_config.sum_vars[0]
    xi = sesh_config.sum_vars[1]
    xiui = sesh_config.sum_vars[2]
    xiyi = sesh_config.sum_vars[3]
    ui = sesh_config.sum_vars[4]
    ui2 = sesh_config.sum_vars[5]
    uiyi = sesh_config.sum_vars[6]



    A = np.array([[xi2 - xi*x_bar, xiui - xi*u_bar], 
                    [xiui - ui*x_bar, ui2 -ui*u_bar]])
    
    ef = np.array([[xiyi - xi*y_bar], [uiyi - ui*y_bar]])
    try: # incase A is singular
        m = np.linalg.inv(A) @ ef 
    except: 
        m = np.array([[0], [0]])
    bias = y_bar - m[0]*x_bar - m[1]*u_bar     # y 
    

    # calculate estimated time
    time_estimate = bias + m[0]*spindle_travel + m[1]*spindle_stops
    
    if sesh_config.avg_n < 5: 
        # use temporary time_estimate because its inaccurate with small amount of samples
        time_estimate = 10*60

    return time_estimate, spindle_travel, spindle_stops

def zero_xy(ser): 
    cmd = f"G92 X0 Y0\n"
    ser.write(str.encode(cmd))
    wait_for_movement_completion(ser, cmd)
    ser.write(b"?")
    string = ser.read(100).decode()

    MPos = string[string.index("M")+5:string.index("W")-1]
    MPos = tuple(float(i) for i in MPos.split(","))

    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))

    new_map = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
    return ser, new_map


def zero_z(ser): 
    cmd = f"G92 Z0\n"
    ser.write(str.encode(cmd))
    wait_for_movement_completion(ser, cmd)
    
    ser.write(b"?")
    string = ser.read(100).decode()

    MPos = string[string.index("M")+5:string.index("W")-1]
    MPos = tuple(float(i) for i in MPos.split(","))

    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))

    new_map = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
    return ser, new_map

def unlock(ser): 
    cmd = "$X\n"
    ser.write(str.encode(cmd))
    return

def print_main_menu():
    time.sleep(2)
    print("-------------------------------------------------------")
    print("Main Console: ")
    print("'1' - unlock machine")
    print("'2' - home and calibrate machine cordinates")
    print("'3' - verify machine cordinate to work cordinate mapping")
    print("'4' - jog spindle ") # included with xero xy and z
    print("'5' - zero xy position")
    print("'6' - zero z position")
    print("'7' - lath spoilboard")
    print("'8' - Write g-code")
    print("'n' - exit")
    return

def generate_preview(stateIdx, gcode_path, plate_num, mapping): 
    # generate preview figure and store in folder first obtain the mPos start and ends of the plate location to better generate preview
    # ---- bed locations ---- (BL corner) all mPos not wPos
    # NSW: (-205.6, -159.6) mm                
    # QLD: (-205.6, -159.6) mm 
    # VIC light: (-205, -159.3) mm
    # VIC heavy: (-205, -153) mm    
    # mapping = wPos - mPos
    # ---- plate dimensions ---- (width x height) in mm
    # NSW: 126 x 71
    # QLD: 126 x 71
    # VIC light: 110 x 59 
    # Vic heavy: 125 x 70


    
    # seems to need to add origin offset
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    pl = [[-205.6, -205.6, -205, -207], [-157.6, -157.6, -153, -158.0]]
    imDim = [[126, 126, 125, 110], [71, 71, 70, 59]]
    today = datetime.now().strftime("%m%d%H%M%S")
    datetimeString = today

    plateImg = plt.imread(f"plates_images/{states[stateIdx]}_ModPlate_Image.jpg")
    with open(gcode_path, 'r') as f: 
         lines = f.readlines()

    x = 0
    y = 0
    xArr = []
    yArr = []
    xChar = []
    yChar = []
    for line in lines: 
        if line.startswith("G1") or line.startswith("G0"): 
            if line.find("Z") != -1 and line.find("F") == -1: 
                # flush last letter and clear array
                xChar.append(xArr)
                yChar.append(yArr)
                xArr = []
                yArr = []

            if line.find("Z") == -1: 
                Xi = line.find("X")
                Yi = line.find("Y")

                if Xi != -1: 
                    x = float(line[Xi+1:Xi+6]) # values are given in 3dp

                if Yi != -1:
                    y = float(line[Yi+1:Yi+6])
            
                # convert x and y to imgPos from wPos
                XmPos = x - mapping[0]
                YmPos = y - mapping[1]
                # NOT NEEDING ORIGIN OFFSET? FLAG
                XimgLocal = XmPos - (pl[0][stateIdx]) # origin offset is added here to shift the preview according to the origin set by the user
                YimgLocal = -(YmPos - (pl[1][stateIdx] + imDim[1][stateIdx])) # negative because img y is flipped compared to mpos y

                Xpx = round(XimgLocal * 5)
                Ypx = round(YimgLocal * 5)


                xArr.append(Xpx)
                yArr.append(Ypx) 


    # plot figure
    plt.figure()  
    plt.imshow(plateImg)
    # plt.axes().set_visible(False)

    for i in range(len(xChar)):
        plt.plot(xChar[i], yChar[i], color='whitesmoke')

    # save file
    directory = f"static/preview/{states[stateIdx]}"
    if not os.path.exists(directory):
        os.makedirs(directory)
    filename = f'platePreview_{datetimeString}_{plate_num}.png' # FLAG datetime string too common if plate_num is fixed
    filepath = os.path.join(directory, filename)
    plt.savefig(filepath)
    plt.close()
    serverpath = directory + "/" + filename

    print("returning server file path")
    return serverpath

def save_default_settings(state_idx, engData, engDataMore): 
    '''
    
    FLAG: currently believed to be functional - review later

    '''
    def safe_float(val): 
        try: 
            return float(val)
        except: 
            if val == "": 
                val = None
                return val
            else:
                raise ValueError(f"Invalid float value: {val}")
        
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    # load default settings
    path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings_default.txt"
    print(engData["cutZ"])
    print(float(engData["cutZ"]))
    zcut = safe_float(engData["cutZ"])
    zsafe = safe_float(engData["safeZ"])
    xorigin = safe_float(engData["originX"])
    yorigin = safe_float(engData["originY"])
    gpostx = safe_float(engData['finalX'])
    gposty = safe_float(engData["finalY"])
    gpostz = safe_float(engData["finalZ"])
    
    gpost = (gpostx, gposty, gpostz)
    origin_offset = (xorigin, yorigin)
    feedRate = safe_float(engDataMore["feedRate"])
    plungeRate = safe_float(engDataMore["plungeRate"])
    textHeight = safe_float(engDataMore["textHeight"])
    lineThickness = safe_float(engDataMore["lineThickness"])
    textWidth = safe_float(engDataMore["textWidth"])
    charSpacing = safe_float(engDataMore["charSpacing"])
    wordSpacing = safe_float(engDataMore["wordSpacing"])
    lineSpacing = safe_float(engDataMore["lineSpacing"])
    textAngle = safe_float(engDataMore["textAngle"])


    # edit settings lines according to provided data
    with open(path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        # modify the cutting depth
        if "ZCUT" in line and zcut is not None:
            # parse with split instead of fixed indices
            parts = line.split()
            # parts: ['(fengrave_set', 'ZCUT', '2', ')']  or similar
            # change the value part (usually index 2)
            # old_depth = parts[2]
            parts[2] = f"{zcut:.3f}"
            # rebuild the line, preserving simple spacing and closing paren
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"
            print(lines[i])

        # modify the safe z height   
        elif "ZSAFE" in line and zsafe is not None:
            parts = line.split()
            parts[2] = f"{zsafe:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}      {parts[2]} )\n"
        
        # modify the x_origin
        elif "xorigin" in line and origin_offset[0] is not None:
            parts = line.split()
            parts[2] = f"{origin_offset[0]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
        
        # modify the y_origin
        elif "yorigin" in line and origin_offset[1] is not None:
            parts = line.split()
            parts[2] = f"{origin_offset[1]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
        
        # modify the finish position 
        elif "gpost" in line and gpost[0] is not None: 
            parts = line.split()
            post_loc = f"X{gpost[0]:.3f} Y{gpost[1]:.3f} Z{gpost[2]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} {post_loc} {parts[6]} {parts[7]}  )\n"

        # add the changes to feed and plunge rate
        elif 'FEED' in line and feedRate is not None: 
            parts = line.split()
            parts[2] = f"{feedRate:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"

        elif 'PLUNGE' in line and plungeRate is not None:
            parts = line.split()
            parts[2] = f"{plungeRate:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"

        elif 'YSCALE' in line and textHeight is not None: 
            parts = line.split()
            parts[2] = f"{textHeight:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif 'STHICK' in line and lineThickness is not None: 
            parts = line.split()
            parts[2] = f"{lineThickness:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif "XSCALE" in line and textWidth is not None: 
            parts = line.split()
            parts[2] = f"{textWidth:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif "CSPACE" in line and charSpacing is not None: 
            parts = line.split()
            parts[2] = f"{charSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif "WSPACE" in line and wordSpacing is not None: 
            parts = line.split()
            parts[2] = f"{wordSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif "LSPACE" in line and lineSpacing is not None: 
            parts = line.split()
            parts[2] = f"{lineSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"


        elif "TANGLE" in line and textAngle is not None: 
            parts = line.split()
            parts[2] = f"{textAngle:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"

    with open(path, "w") as f:
        f.writelines(lines)


def generate_gcode_web(state_idx, text_path, plate_num, engData, engDataMore, verbose=True): 
    def safe_float(val): 
        try: 
            val = float(val)
        except: 
            if val == "": 
                val = None
            else:
                raise ValueError(f"Invalid float value: {val}")
        return val
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    # modify the settings file with depth and z_safe requirements
    path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings.txt"

    zcut = safe_float(engData["cutZ"])
    zsafe = safe_float(engData["safeZ"])
    xorigin = safe_float(engData["originX"])
    yorigin = safe_float(engData["originY"])
    gpostx = safe_float(engData['finalX'])
    gposty = safe_float(engData["finalY"])
    gpostz = safe_float(engData["finalZ"])
    
    gpost = (gpostx, gposty, gpostz)
    origin_offset = (xorigin, yorigin)
    feedRate = safe_float(engDataMore["feedRate"])
    plungeRate = safe_float(engDataMore["plungeRate"])
    textHeight = safe_float(engDataMore["textHeight"])
    lineThickness = safe_float(engDataMore["lineThickness"])
    textWidth = safe_float(engDataMore["textWidth"])
    charSpacing = safe_float(engDataMore["charSpacing"])
    wordSpacing = safe_float(engDataMore["wordSpacing"])
    lineSpacing = safe_float(engDataMore["lineSpacing"])
    textAngle = safe_float(engDataMore["textAngle"])
    # FLAG
    # post script Gcode and pre-script gcode currently not in use as they are encoded with Gcode origin and final work position


    # edit settings lines according to provided data
    with open(path, "r") as f:
        lines = f.readlines()




    curr_config = {"ZCUT": zcut, "ZSAFE": zsafe, "XORIGIN": xorigin, "YORIGIN": yorigin, "GPOST": gpost}

    for i, line in enumerate(lines):
        # modify the cutting depth
        if "ZCUT" in line and zcut is not None:
            if verbose: 
                print("OLD:", line.strip())
            # parse with split instead of fixed indices
            parts = line.split()
            # parts: ['(fengrave_set', 'ZCUT', '2', ')']  or similar
            # change the value part (usually index 2)
            # old_depth = parts[2]
            parts[2] = f"{zcut:.3f}"
            # rebuild the line, preserving simple spacing and closing paren
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        # modify the safe z height   
        elif "ZSAFE" in line and zsafe is not None:
            if verbose: 
                print("OLD:", line.strip())
            parts = line.split()
            parts[2] = f"{zsafe:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}      {parts[2]} )\n"
            if verbose:
                print("NEW:", lines[i].strip())
        
        # modify the x_origin
        elif "xorigin" in line and origin_offset[0] is not None:
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[0]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())
        
        # modify the y_origin
        elif "yorigin" in line and origin_offset[1] is not None:
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[1]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())
        
        # modify the finish position 
        elif "gpost" in line and gpost[0] is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            post_loc = f"X{gpost[0]:.3f} Y{gpost[1]:.3f} Z{gpost[2]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} {post_loc} {parts[6]} {parts[7]}  )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        # add the changes to feed and plunge rate
        elif 'FEED' in line and feedRate is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{feedRate:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif 'PLUNGE' in line and plungeRate is not None:
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{plungeRate:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())
        
        elif 'YSCALE' in line and textHeight is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{textHeight:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif 'STHICK' in line and lineThickness is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{lineThickness:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif "XSCALE" in line and textWidth is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{textWidth:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif "CSPACE" in line and charSpacing is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{charSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif "WSPACE" in line and wordSpacing is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{wordSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif "LSPACE" in line and lineSpacing is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{lineSpacing:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        elif "TANGLE" in line and textAngle is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{textAngle:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}     {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

            

    with open(path, "w") as f:
        f.writelines(lines)

    # generate gcode
    gcode_path = f"/home/pi/Documents/F-Engrave-1.76_src/output/{datetime.now()}_{plate_num}.ngc"
    cmd = f'''
    eng_text="$(<"{text_path}")"

    xvfb-run -a python3 \
    "/home/pi/Documents/F-Engrave-1.76_src/f-engrave.py" \
    -g "/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings.txt" \
    -f "/home/pi/Documents/F-Engrave-1.76_src/fonts/normal.cxf" \
    -t "$eng_text" \
    -b \
    > "{gcode_path}"
    '''

    subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    return gcode_path, curr_config


def generate_gcode(state_idx, text_path, plate_num, depth=None, z_safe=None, origin_offset=None, finish_position=(0,115,15), verbose=False): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    # modify the settings file with depth and z_safe requirements
    path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings.txt"

    with open(path, "r") as f:
        lines = f.readlines()

    # just to read the lines
    for i, line in enumerate(lines): 
        if "ZCUT" in line: 
            if verbose: 
                print("Current cutting depth line:", line.split()[2])
            zcut = float(line.split()[2])
        if "ZSAFE" in line:
            if verbose: 
                print("Current safe z height line:", line.split()[2])
            zsafe = float(line.split()[2])
        if "xorigin" in line: 
            if verbose: 
                print("Current x origin line:", line.split()[2])
            xorigin = float(line.split()[2])
        if "yorigin" in line:
            if verbose: 
                print("Current y origin line:", line.split()[2])
            yorigin = float(line.split()[2])
        if "gpost" in line:
            if verbose: 
                print("Current finish position line:", line.split()[3], line.split()[4], line.split()[5])
            gpostx = float(line.split()[3][1:])
            gposty = float(line.split()[4][1:])
            gpostz = float(line.split()[5][1:])
            gpost = (gpostx, gposty, gpostz)

    curr_config = {"ZCUT": zcut, "ZSAFE": zsafe, "XORIGIN": xorigin, "YORIGIN": yorigin, "GPOST": gpost}

    for i, line in enumerate(lines):
        # modify the cutting depth
        if "ZCUT" in line and depth is not None:
            if verbose: 
                print("OLD:", line.strip())
            # parse with split instead of fixed indices
            parts = line.split()
            # parts: ['(fengrave_set', 'ZCUT', '2', ')']  or similar
            # change the value part (usually index 2)
            # old_depth = parts[2]
            parts[2] = f"{depth:.3f}"
            # rebuild the line, preserving simple spacing and closing paren
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())

        # modify the safe z height   
        elif "ZSAFE" in line and z_safe is not None:
            if verbose: 
                print("OLD:", line.strip())
            parts = line.split()
            parts[2] = f"{z_safe:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}      {parts[2]} )\n"
            if verbose:
                print("NEW:", lines[i].strip())
        
        # modify the x_origin
        elif "xorigin" in line and origin_offset is not None:
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[0]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())
        
        # modify the y_origin
        elif "yorigin" in line and origin_offset is not None:
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[1]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            if verbose: 
                print("NEW:", lines[i].strip())
        
        # modify the finish position 
        elif "gpost" in line and finish_position is not None: 
            if verbose: 
                print("OLD: ", line.strip())
            parts = line.split()
            post_loc = f"X{finish_position[0]:.3f} Y{finish_position[1]:.3f} Z{finish_position[2]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} {post_loc} {parts[6]} {parts[7]}  )\n"
            if verbose: 
                print("NEW:", lines[i].strip())




            

    with open(path, "w") as f:
        f.writelines(lines)

    # generate gcode
    gcode_path = f"/home/pi/Documents/F-Engrave-1.76_src/output/{datetime.now()}_{plate_num}.ngc"
    cmd = f'''
    eng_text="$(<"{text_path}")"

    xvfb-run -a python3 \
    "/home/pi/Documents/F-Engrave-1.76_src/f-engrave.py" \
    -g "/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings.txt" \
    -f "/home/pi/Documents/F-Engrave-1.76_src/fonts/normal.cxf" \
    -t "$eng_text" \
    -b \
    > "{gcode_path}"
    '''

    subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    return gcode_path, curr_config

# web based version that takes in inputs as a df already
def generate_engraving_text_web(state_idx, plate_num, json, verbose=False): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]

    template_path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/text.txt"
    modtext_path = f"/home/pi/Documents/F-Engrave-1.76_src/output/eng_text_{datetime.now()}_{plate_num}_{states[state_idx]}.txt"

    with open(template_path, "r") as f: 
        template_lines = f.readlines()

    # convert json to list
    values = list(json.values())
    
    # NSW (CAPS/no comma format and will always be so)
    if state_idx == 0: 
        # filters values for commas and get rid of them for full stops
        values = [value.replace(",", ".") if isinstance(value, str) else value for value in values]


        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 7: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline
    

    # QLD plates (comma format)
    elif state_idx == 1: 
        # convert the GVM and GCM values to comma format for the calibration to work  BUG: input count is last number
        if str(values[-5]).find(",") == -1: 
            try: 
                modGVM = int(values[-4])
                values[-4] = f"{modGVM:,}"
            except: 
                pass
        
        if str(values[-4]).find(",") == -1:
            try: 
                modGCM = int(values[-3])
                values[-3] = f"{modGCM:,}" 
            except: 
                pass

        if str(values[-2]).find(",") == -1:
            try: 
                modATM = int(values[-1])
                values[-1] = f"{modATM:,}"
            except: 
                pass
        
        if str(values[-3]).find(",") == -1:
            try: 
                modGTM = int(values[-2])
                values[-2] = f"{modGTM:,}"
            except: 
                pass
        


        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 2: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 3: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 5:
                    verbose and print(f"i: {i}, j: {j}, k: {k}")
                    newline = newline + space_tokens[0] + values[j] + "\n"
                    # newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1
                    modtext_lines[i] = newline  
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline


    # vic heavy plate (comma format)
    elif state_idx == 2: 
        # convert the GVM and GCM values to comma format for the calibration to work 
        if str(values[-3].find(",")) == -1: 
            try: 
                if values[-3] != "":
                    modGVM = int(values[-3])
                    values[-3] = f"{modGVM:,}"
            except: 
                pass
        
        if str(values[-2].find(",")) == -1:
            try: 
                if values[-2] != "": 
                    modGCM = int(values[-2])
                    values[-2] = f"{modGCM:,}"

            except:
                pass


        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i not in [1, 8]: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 2: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 4:  # tyre size line with front and rear
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + "\n"
                    j += 1
                    modtext_lines[i] = newline                    
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            elif i == 8: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0]
                newline = newline + "\n"
                modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline

    # VIC light plate (comma format and could be)
    elif state_idx == 3: 
        # convert the GVM and GCM values to comma format for the calibration to work 
        if str(values[-3].find(",")) == -1: 
            try: 
                if values[-3].isdigit(): 
                    modGVM = int(values[-3])
                    values[-3] = f"{modGVM:,}"
            except:
                pass
        if str(values[-2].find(",")) == -1:
            try: 
                if values[-2].isdigit():
                    modGCM = int(values[-2])
                    values[-2] = f"{modGCM:,}" 
            except: 
                pass
        

        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 4:  # line with mod codes
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                # exclude the \n at the end
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline


    with open(modtext_path, "w") as f:
         f.writelines(modtext_lines)





    return modtext_path, modtext_lines



# works
def generate_engraving_text(state_idx, plate_num, verbose=False): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]

    template_path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/text.txt"
    modtext_path = f"/home/pi/Documents/F-Engrave-1.76_src/output/eng_text_{datetime.now()}_{plate_num}_{states[state_idx]}.txt"

    with open(template_path, "r") as f: 
        template_lines = f.readlines()

    print("------------------------------------------------------")
    print(f"Please input the details of the {states[state_idx]} plate, and press 'Enter'. ")
    
    # NSW (CAPS/no comma format and will always be so)
    if state_idx == 0: 
        lsc_num = str(input("Licence Number (press Enter for 130009): "))
        if lsc_num == "": 
            lsc_num = "130009"
        date = str(input("Date (Press Enter for TODAY): ")) # can make this automatic
        if date == "": 
            today = str(datetime.now()).split()[0].split("-")  # extract the date, then split to extract y-m-d
            date = f"{today[2]}/{today[1]}/{today[0]}" # convert to d-m-y
            # print(date)
        cert_num = str(input("Certification Number: "))
        VIN = str(input("VIN: "))
        Eng_num = str(input("Engine Number: "))
        Seat_cap = str(input("Seating Capacity: "))
        front_tyre = str(input("Tyre Size: Front  "))
        rear_tyre = str(input("Tyre Size: Rear  "))
        modGVM = str(input("Modification GVM: "))
        modGCM = str(input("Modification GCM: "))
        modGTM = str(input("Modification GTM (press Enter if unspecified): "))
        if modGTM == "": 
            modGTM = "----"
        modATM = str(input("Modification ATM (press Enter if unspecified): "))
        if modATM == "": 
            modATM = "----"
        modCode = str(input("Modification Codes (seperate with '. '): ")) # might get comma, write a function to chop it up to just seperated by fullstops
        
        # if modGVM == "":
        #     modGVM = "   "
        # if front_tyre == "":
        #     front_tyre = "       "
        # if engine_num == "":
        #     engine_num = "        " # find out a way to measure the length of this so that the spacing is always correct
        # if lsc_num == "":
        #     lsc_num = "    "

        # filters values for commas and get rid of them for full stops
        lsc_num = lsc_num.replace(",", ".")
        date = date.replace(",", ".")
        cert_num = cert_num.replace(",", ".")
        VIN = VIN.replace(",", ".")
        Eng_num = Eng_num.replace(",", ".")
        Seat_cap = Seat_cap.replace(",", ".")
        front_tyre = front_tyre.replace(",", ".")
        rear_tyre = rear_tyre.replace(",", ".")
        modGVM = modGVM.replace(",", ".")
        modGCM = modGCM.replace(",", ".")
        modGTM = modGTM.replace(",", ".")
        modATM = modATM.replace(",", ".")
        modCode = modCode.replace(",", ".")


        values = [lsc_num, date, cert_num, VIN, Eng_num, Seat_cap, front_tyre, rear_tyre, modGVM, modGCM, modGTM, modATM, modCode]
        if verbose: 
            print(values[12])
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 7: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline
    
    # QLD plates (comma format)
    elif state_idx == 1: 
        lsc_num = str(input("Accreditation No: "))
        date = str(input("Date (Press Enter for TODAY): ")) # can make this automatic
        if date == "": 
            today = str(datetime.now()).split()[0].split("-")  # extract the date, then split to extract y-m-d
            date = f"{today[2]}/{today[1]}/{today[0]}" # convert to d-m-y
            # print(date)
        cert_num = str(input("Certification Number: "))
        Mod_bod = str(input("Modification By: "))
        modCode = str(input("Modification Codes (seperate with '. '): ")) # might get comma, write a function to chop it up to just seperated by fullstops
        VIN = str(input("VIN: "))
        tyre_size = str(input("Tyre Size(If both front & Rear please type Front: size Rear: size):  "))
        # tyre_size = str(input("Tyre Size: "))
        Seat_cap = str(input("Seating Capacity: "))
        modGVM = str(input("Modification GVM: "))
        modGCM = str(input("Modification GCM: "))
        modGTM = str(input("Modification GTM (press Enter if unspecified): "))
        if modGTM == "": 
            modGTM = "----"
        modATM = str(input("Modification ATM (press Enter if unspecified): "))
        if modATM == "": 
            modATM = "----"
        
        # convert the GVM and GCM values to comma format for the calibration to work 
        if modGVM.find(",") == -1: 
            modGVM = int(modGVM)
            modGVM = f"{modGVM:,}"
        
        if modGCM.find(",") == -1:
            modGCM = int(modGCM)
            modGCM = f"{modGCM:,}" 
        
        values = [lsc_num, date, cert_num, Mod_bod, modCode, VIN, tyre_size, Seat_cap, modGVM, modGCM, modGTM, modATM]
        # print(values[12])
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 2: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 3: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 5:
                    verbose and print(f"i: {i}, j: {j}, k: {k}")
                    newline = newline + space_tokens[0] + values[j] + "\n"
                    # newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1
                    modtext_lines[i] = newline  
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline

    # vic heavy plate (comma format)
    elif state_idx == 2: 
        lsc_num = str(input("VASS Certificate No: "))
        date = str(input("Date (Press Enter for TODAY): ")) # can make this automatic
        if date == "": 
            today = str(datetime.now()).split()[0].split("-")  # extract the date, then split to extract y-m-d
            date = f"{today[2]}/{today[1]}/{today[0]}" # convert to d-m-y
            # print(date)
        modCode = str(input("Modification Codes (seperate with '. '): ")) # might get comma, write a function to chop it up to just seperated by fullstops
        VIN = str(input("VIN: "))
        tyre_size = str(input("Tyre Size(If both front & Rear please type 'Front: size    Rear: size'):  "))
        Mod_axles = str(input("Modified Number of Axles: "))
        ADR_cat = str(input("ADR CAT: "))
        Seat_cap = str(input("Seating Capacity: "))
        bod_style = str(input("Body Style: "))
        modGVM = str(input("Modification GVM/ATM: "))
        modGCM = str(input("Modification GCM/GTM: "))
        ser_no = str(input("Serial Number: "))
        
        # convert the GVM and GCM values to comma format for the calibration to work 
        if modGVM.find(",") == -1: 
            if modGVM != "":
                modGVM = int(modGVM)
                modGVM = f"{modGVM:,}"
        
        if modGCM.find(",") == -1:
            if modGCM != "": 
                modGCM = int(modGCM)
                modGCM = f"{modGCM:,}" 

        
        values = [lsc_num, date, modCode, VIN, tyre_size, 
                  Mod_axles, ADR_cat, Seat_cap, bod_style, modGVM, modGCM, ser_no]

        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i not in [1, 8]: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 2: 
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 4:  # tyre size line with front and rear
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + "\n"
                    j += 1
                    modtext_lines[i] = newline                    
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            elif i == 8: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0]
                newline = newline + "\n"
                modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline

    # VIC light plate (comma format and could be)
    elif state_idx == 3: 
        ste = str(input("State: "))
        date = str(input("Date (Press Enter for TODAY): ")) # can make this automatic
        if date == "": 
            today = str(datetime.now()).split()[0].split("-")  # extract the date, then split to extract y-m-d
            date = f"{today[2]}/{today[1]}/{today[0]}" # convert to d-m-y
            # print(date)
        cert_num = str(input("VASS Certification Number: "))
        yr_mk_mod = str(input("Year/Make/Model: "))
        VIN = str(input("VIN/Chassis Number: "))
        Seat_cap = str(input("Seating Capacity: "))
        ADR_cat = str(input("ADR Category: "))
        bod_style = str(input("Body Style: "))
        modCode = str(input("Modification Codes (seperate with '. '): ")) # might get comma, write a function to chop it up to just seperated by fullstops
        modGVM = str(input("Modification GVM: "))
        modGCM = str(input("Modification GCM: "))        
        ser_no = str(input("Reference/Serial Number: "))
        
        # convert the GVM and GCM values to comma format for the calibration to work 
        if modGVM.find(",") == -1: 
            if modGVM.isdigit(): 
                modGVM = int(modGVM)
                modGVM = f"{modGVM:,}"
        if modGCM.find(",") == -1:
            if modGCM.isdigit():
                modGCM = int(modGCM)
                modGCM = f"{modGCM:,}" 
        
        values = [ste, date, cert_num, yr_mk_mod, VIN, Seat_cap, ADR_cat, bod_style, modCode, modGVM, modGCM, ser_no]
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                if i == 4:  # line with mod codes
                    verbose and print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        verbose and print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                verbose and print(stuff_tokens, space_tokens)
                # exclude the \n at the end
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline


    with open(modtext_path, "w") as f:
         f.writelines(modtext_lines)


    # print(template_lines)


    return modtext_path, modtext_lines



def get_plate_num(state, textData): 
    # generate the plate serial number from scarch if not already provided
    # state is a str within [QLD, NSW, VIC_Heavy, VIC_Light]
    # textData is a json
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    if textData["plateSerialNumber"] != "":
        return str(textData["plateSerialNumber"])
    else: 
        if state == "VIC_Heavy" and textData["SerNo"] != "": 
            return str(textData["SerNo"]) # use inbuilt ser number when allowed
        elif state == "VIC_Light" and textData["SerNo"] != "": 
            return str(textData["SerNo"])
        else: 
            config_path = "/home/pi/Documents/Engraving_codebase/script_config.json"
            with open(config_path, "r") as f:
                config_dict = json.load(f)
                sesh_config = config(**config_dict)  # unpacking dictionary to config dataclass

                idx = states.index(state)

                if idx != -1:
                    plate_num = sesh_config.plate_counter[idx] + 1
                    sesh_config.plate_counter[idx] = plate_num

                    with open(config_path, "w") as f: 
                        # convert config dataclass to dictionary 
                        json.dump(asdict(sesh_config), f, indent=4)

                    return str(plate_num)
                else:
                    print("State not found, cannot generate plate number.")
                    return "000000"

def main(verbose=False):
    # code status: all seperate code tested and working universal mapping synchronisation between calibration not yet verified - need to test pyplot function
    config_path = "/home/pi/Documents/Engraving_codebase/script_config.json"
    with open(config_path, "r") as f:
        config_dict = json.load(f)
        sesh_config = config(**config_dict)  # unpacking dictionary to config dataclass
    mapping = None
    print("CnC controller V1.0 for 3018 desktop Engraver. ")
    print("Written by: Roger Luo - 15/12/2025")
    print("-------------------------------------------------------")
    port = scan_grbl_port(115200)
    ser = send_wakeup(port=port)
    print("-------------------------------------------------------")
    print("Main Console: ")
    print("'1' - unlock machine")
    print("'2' - home and calibrate machine cordinates")
    print("'3' - verify machine cordinate to work cordinate mapping") # a bit sticky for some reason
    print("'4' - jog spindle ") # included with xero xy and z
    print("'5' - zero xy position")
    print("'6' - zero z position")
    print("'7' - lath spoilboard")
    print("'8' - Engrave Plate")
    print("'n' - exit")
    # mapping = (198.1, 179.801, 22.581)
    # wPos = (0, 125, 15)
    keyboardInput = getch().lower()
    
    if sesh_config.islath:
        mapping = sesh_config.mapping_lath
    else:
        mapping = sesh_config.mapping_work

    # move to last finished work Position
    try: 
        unlock(ser)  
        ser = homeNcalibrate(ser, mapping, sesh_config.finish_wPos, verbose=verbose)
        print_main_menu()
    except: 
        print("Homing Failed, please ensure there are no obstructions and try again.")
        print_main_menu()



    while keyboardInput != "n":
        keyboardInput = getch().lower()
        if keyboardInput == "1": 
            try: 
                unlock(ser)
                print("Machine Unlocked!")
                print_main_menu()
            except: 
                print("Unlock Failed, check if E-stop is pressed and try again. ")
                print_main_menu()
        if keyboardInput == "2": 
            try: 
                ser = homeNcalibrate(ser, mapping, sesh_config.wPos_home, verbose=verbose)
                print_main_menu()
            except: 
                print("Homing Failed, please ensure there are no obstructions and try again.")
                print_main_menu()
        if keyboardInput == "3": 
            try: 
                ser = verify_wPos(ser, sesh_config.mapping_work, verbose=verbose)
                print_main_menu()
            except: 
                print("Verification Failed.")
                print_main_menu()
        if keyboardInput == "4": 
            try: 
                islath = input("Calibhrating Lath zero position? (y/n): ").lower()
                if islath == "y":
                    ser, mapping = jog(ser, sesh_config.mapping_lath)
                    sesh_config.mapping_lath = mapping
                    sesh_config.islath = True
                if islath != "y":
                    ser, mapping = jog(ser, sesh_config.mapping_work)
                    sesh_config.mapping_work = mapping     
                    sesh_config.islath = False         

                with open(config_path, "w") as f: 
                    # convert config dataclass to dictionary 
                    json.dump(asdict(sesh_config), f, indent=4)
                print_main_menu()
            except: 
                print("Jog Failed, please try again.")
                print_main_menu()
        if keyboardInput == "5": 
            try: 
                ser, mapping = zero_xy(ser)
                sesh_config.mapping_work = mapping

                with open(config_path, "w") as f:
                    # convert config dataclass to dictionary 
                    json.dump(asdict(sesh_config), f, indent=4)
                print_main_menu()
            except:
                print("Zeroing Failed, please try again.")
                print_main_menu()
        if keyboardInput == "6": 
            try: 
                ser, mapping = zero_z(ser)
                sesh_config.mapping_work = mapping
                with open(config_path, "w") as f:
                    # convert config dataclass to dictionary 
                    json.dump(asdict(sesh_config), f, indent=4)
                print_main_menu()
            except: 
                print("Zeroing Failed, please try again. ")
                print_main_menu()
        if keyboardInput == "7": 
            try: 
                depth = float(input("Input the lath depth (mm) and press enter: "))
                bed_dim_1 = float(input("Input the bed width (mm) and press enter: "))
                bed_dim_2 = float(input("Input the bed height (mm) and press enter: "))
                sesh_config.beddim = (bed_dim_1, bed_dim_2)
                with open(config_path, "w") as f:  
                    # convert config dataclass to dictionary 
                    json.dump(asdict(sesh_config), f, indent=4)

                _ = input("Please check that a Flat drillbit is installed, and press Enter. ")
                bed_dim = (bed_dim_1, bed_dim_2)
                if mapping: 
                    sesh_config.mapping_lath = mapping # stores the mapping if it's been changed
                _, gcode_path, _ = calibrate_spoilboard(depth, bed_dim)
                write_gcode(ser, gcode_path, sesh_config.mapping_lath, verbose=verbose)

                # edit the mapping to reflect the new z height 
                sesh_config.mapping_lath = (sesh_config.mapping_lath[0], sesh_config.mapping_lath[1], sesh_config.mapping_lath[2] + abs(depth))
                sesh_config.mapping_work = (sesh_config.mapping_work[0], sesh_config.mapping_work[1], sesh_config.mapping_work[2] + abs(depth))
                with open(config_path, "w") as f:
                    # convert config dataclass to dictionary 
                    json.dump(asdict(sesh_config), f, indent=4)
                print_main_menu()
            except: 
                print("Input errpr, please try again ")
                print_main_menu()
        if keyboardInput == "8":
            print("---------------------------------------")
            print("1 - NSW \n2 - QLD \n3- VIC_Heavy\n4 - VIC_Light")
            while True: 
                try: 
                    state_idx =  int(input("Please select the plate type: ")) - 1
                    plate_num = input("Please input plate serial number(press enter for default): ")
                    if plate_num == "": 
                        plate_num = f"{sesh_config.year}_{state_idx}{(sesh_config.plate_counter[state_idx] + 1):03d}"
                        sesh_config.plate_counter = list(sesh_config.plate_counter)
                        sesh_config.plate_counter[state_idx] += 1
                        sesh_config.plate_counter = tuple(sesh_config.plate_counter)
                        verbose and print(plate_num)
                        with open(config_path, "w") as f:
                            # convert config dataclass to dictionary 
                            json.dump(asdict(sesh_config), f, indent=4)
                    # make a JSON and a way to read the plate_num
                    else: 
                        plate_num = int(plate_num)
                    break
                except KeyboardInterrupt: 
                    break
                except: 
                    print("Serial number unavaliable or state not found, please try again")


            # generate the text
            try: 
                eng_textpath, eng_textlines = generate_engraving_text(state_idx, plate_num, verbose=verbose)
            except: 
                print("Error generating engraving text, please try again.")
                print_main_menu()
                continue
            # check if engraving settings need to be changed
            while True: 
                try: 
                    depth = input("Enter cutting depth in mm (press Enter for default): ")
                    z_safe = input("Enter new safe z height in mm (press Enter for default): ")
                    origin_offset = input("Enter new origin offset as 'x,y' in mm (press Enter for default): ")
                    finish_position = input("Enter new finish position as 'x,y,z' in mm (press Enter for default): ")
                    if finish_position == "": 
                        finish_position = (0,115,15)
                    else: 
                        finish_position = tuple(float(i) for i in finish_position.split(","))
                    if depth == "": 
                        depth = None
                    else: 
                        depth = float(depth)
                    if z_safe == "":
                        z_safe = None
                    else: 
                        z_safe = float(z_safe)
                    if origin_offset == "":
                        origin_offset = None
                    else: 
                        origin_offset = tuple(float(i) for i in origin_offset.split(","))
                    break
                except KeyboardInterrupt: 
                    break
                except: 
                    print("Input error, please check your input and try again. ")
            # write the gcode
            try:
                gcode_path, curr_config = generate_gcode(state_idx, eng_textpath, plate_num, 
                                                         depth=depth, z_safe=z_safe, 
                                                         origin_offset=origin_offset, 
                                                         finish_position=finish_position, 
                                                         verbose=verbose)
            except: 
                print("Error generating gcode, please try again.")
                print_main_menu()
                continue
            print("Engraving...")
            write_gcode(ser, gcode_path, verbose=verbose)
            
            # again function to re-engrave if required
            print("---------------------------------------")
            print("Engraving Complete!")
            print(f"Current Config: \n ZSAFE:  {curr_config['ZSAFE']} \n ZCUT: {curr_config['ZCUT']} \n XORIGIN: {curr_config['XORIGIN']} \n YORIGIN: {curr_config['YORIGIN']} \n GPOST: {curr_config['GPOST']} ")
            again = input("Please check Engraving quality. Press 'y' if satisfactory, 'n' to repeat: ").lower()

            while again != "y":
                try: 
                    depth = input("Enter cutting depth in mm (press Enter for default): ")
                    z_safe = input("Enter new safe z height in mm (press Enter for default): ")
                    origin_offset = input("Enter new origin offset as 'x,y' in mm (press Enter for default): ")
                    finish_position = input("Enter new finish position as 'x,y,z' in mm (press Enter for default): ")
                    if finish_position == "": 
                        finish_position = (0,115,15)
                    else: 
                        finish_position = tuple(float(i) for i in finish_position.split(","))
                    if depth == "": 
                        depth = None
                    else: 
                        depth = float(depth)
                    if z_safe == "":
                        z_safe = None
                    else: 
                        z_safe = float(z_safe)
                    if origin_offset == "":
                        origin_offset = None
                    else: 
                        origin_offset = tuple(float(i) for i in origin_offset.split(","))
                    # write the gcode
                    try:
                        gcode_path, curr_config = generate_gcode(state_idx, eng_textpath, plate_num, 
                                                                 depth=depth, z_safe=z_safe, 
                                                                 origin_offset=origin_offset, 
                                                                 finish_position=finish_position,
                                                                 verbose=verbose)
                    except: 
                        print("Error generating gcode, please try again.")
                        print_main_menu()
                        continue
                    write_gcode(ser, gcode_path, verbose=verbose)

                    print("---------------------------------------")
                    print("Engraving Complete!")
                    print(f"Current Config: \n ZSAFE:  {curr_config['ZSAFE']} \n ZCUT: {curr_config['ZCUT']} \n XORIGIN: {curr_config['XORIGIN']} \n YORIGIN: {curr_config['YORIGIN']} \n GPOST: {curr_config['GPOST']} ")
                    again = input("Please check Engraving quality. Press 'y' if satisfactory, 'n' to repeat: ").lower()
                except KeyboardInterrupt: 
                    break
                except: 
                    print("Input error, please try again. ")

            print_main_menu()




    # exiting scripts
    ser.write(b"?\n")
    string = ser.read(100).decode()
    MPos = string[string.index("M")+5:string.index("W")-1]
    MPos = tuple(float(i) for i in MPos.split(","))
    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))
    print("Final Machine Position: ", MPos)
    print("Final Work Position: ", WPos)
    print("Final Mapping (WPos - MPos): ", (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2]))
    
    sesh_config.finish_wPos = WPos
    with open(config_path, "w") as f:
        # convert config dataclass to dictionary 
        json.dump(asdict(sesh_config), f, indent=4)
    ser.close()

        
    print("Exiting program. Current work cordinates and machine cordinates saved.")
    print("-------------------------------------------------------------------------------")       
    


if __name__=="__main__": 
    main(verbose=False)