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


import serial
import time
import glob
from threading import Event 
import math
from datetime import datetime
from datetime import timedelta
import subprocess
import os
import re
from dataclasses import dataclass, asdict, is_dataclass
import json
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
        ser.write(b"\r\n\r\n")
        time.sleep(1)
        ser.reset_input_buffer()
        return ser


def verify_wPos(ser, mapping=(193.001, 172.801, 28.521)): 
    # wPos to mPos mapping
    # mapping = wPos - mPos 
    ser.reset_input_buffer()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()
    ser.write(b"?") # probes Mpos
    time.sleep(2)
    string = ser.read(100).decode()
    print(string)

    MPos = string[string.index("M")+5:string.index("W")-1]
    MPos = tuple(float(i) for i in MPos.split(","))

    WPos = string[int(string.index("W")+5):string.index(">")]
    WPos = tuple(float(i) for i in WPos.split(","))

    cur_map = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
    print("string response read as: ", string)
    print("Machine cordinate: ", MPos)
    print("Work cordinates: ", WPos)

    if (abs(cur_map[0] - mapping[0]) >= 0.1) or (abs(cur_map[1] - mapping[1]) >= 0.1) or (abs(cur_map[2] - mapping[2]) >= 0.1): 
        print("Machine Position Inaccurate..")
        print(f"difference : {abs(cur_map[0] - mapping[0])}, {abs(cur_map[1] - mapping[1])}, {abs(cur_map[2] - mapping[2])}")
        print("Recalibrating...")

        homeNcalibrate(ser, mapping=mapping)

    else: 
        print("Machine Position Accurate. ")
        return ser
    
    return ser


def homeNcalibrate(ser, mapping=(193.001, 172.801, 28.521), wPos=(0, 125, 25)):
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
    time.sleep(1) # NEED /n to execute the command

    wait_for_movement_completion(ser,"$H\n")
    print("moving to home")
    mPos = (wPos[0] - mapping[0], wPos[1] - mapping[1], wPos[2] - mapping[2])
    home_cmd = f"G53 X{mPos[0]:.3f} Y{mPos[1]:.3f} Z{mPos[2]:.3f}\n"
    ser.write(str.encode(home_cmd))
    print(home_cmd)
    wait_for_idle(ser)
    print("wait done")
    time.sleep(2)
    print("moving to work")
    work_cmd = f"G92 X{wPos[0]:.3f} Y{wPos[1]:.3f} Z{wPos[2]:.3f}\n"
    print(work_cmd)
    ser.write(str.encode(work_cmd))
    wait_for_idle(ser)
    return ser


def wait_for_movement_completion(ser, clean_cmd_line): 
    # Event().wait(1)
    ser.reset_input_buffer()
    if clean_cmd_line not in ("$X", "$$"): 
        cmd_out = ser.readline().strip().decode()
        print(f"immediete out : {cmd_out}")
        while cmd_out != "ok": 
            # print("inside loop")
            if "alarm" in cmd_out.lower():
                print("Machine in Alarm state!")
                print("cmd out:", cmd_out)

            
            if "error" in cmd_out:
                # print the error out
                print(f"ERROR sending {clean_cmd_line}: {cmd_out}")
            elif "hard" in cmd_out.lower(): 
                print("Hard Limit reached! Manually move spindle away from limit switches and restart.")
                break
            cmd_out = ser.readline().strip().decode()
            print(cmd_out)
        
        return None

def wait_for_idle(ser): 
    while True:
        ser.write(b"?")
        time.sleep(0.1)
        status = ser.readline().decode()
        if "<Idle" in status:
            return

def write_gcode(ser, g_code_path):
    file = open(g_code_path,'r')
    print("file opened")
    # send wakeup to ser
    ser.write(b'\r\n\r\n') 
    time.sleep(1)
    print("going to x0y0")
    ser.write(str.encode("G0 X0 Y0 Z10" + "\n"))
    time.sleep(10)
    print("went to X0 Y0")
    ser.write(str.encode("G0 X90 Y49 Z10" + "\n"))
    print("went to 'M'")
    # check work cordinate mapping
    # verify_wPos(ser, mapping)
    for line in file: 
        cleaned_line = remove_eol_chars(remove_comments(line))

        if cleaned_line:  # ensure that it is not None
            # print("sending G-code: " + str(cleaned_line))

            ser.write(str.encode(cleaned_line + "\n"))
            

            wait_for_movement_completion(ser, cleaned_line)

        
    print("End")
    return


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

import math
from datetime import datetime, timedelta

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
    print("use 'ws' to move the spindle in the positive and negative y direction. ")
    print("use 'ad' to move the spindle in the positive and negative x direction. ")
    print("use 'qe' to move the spindle in the up and down z direction. ")
    print("use 'n' to exit jog mode. ")
    print("use 'm' to switch jog speeds: ")
    print("use 'b' to zero xy cordinates")
    print("use 'v' to zero z cordinates")
    print("use 'x' to toggle on spindle")
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

def generate_gcode(state_idx, text_path, plate_num, depth=None, z_safe=None, origin_offset=None, finish_position=(0,125,20)): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    # modify the settings file with depth and z_safe requirements
    path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/settings.txt"

    with open(path, "r") as f:
        lines = f.readlines()

    # just to read the lines
    for i, line in enumerate(lines): 
        if "ZCUT" in line: 
            print("Current cutting depth line:", line.split()[2])
            zcut = float(line.split()[2])
        if "ZSAFE" in line:
            print("Current safe z height line:", line.split()[2])
            zsafe = float(line.split()[2])
        if "xorigin" in line: 
            print("Current x origin line:", line.split()[2])
            xorigin = float(line.split()[2])
        if "yorigin" in line:
            print("Current y origin line:", line.split()[2])
            yorigin = float(line.split()[2])
        if "gpost" in line:
            print("Current finish position line:", line.split()[3], line.split()[4], line.split()[5])
            gpostx = float(line.split()[3][1:])
            gposty = float(line.split()[4][1:])
            gpostz = float(line.split()[5][1:])
            gpost = (gpostx, gposty, gpostz)

    curr_config = {"ZCUT": zcut, "ZSAFE": zsafe, "XORIGIN": xorigin, "YORIGIN": yorigin, "GPOST": gpost}

    for i, line in enumerate(lines):
        # modify the cutting depth
        if "ZCUT" in line and depth is not None:
            print("OLD:", line.strip())
            # parse with split instead of fixed indices
            parts = line.split()
            # parts: ['(fengrave_set', 'ZCUT', '2', ')']  or similar
            # change the value part (usually index 2)
            # old_depth = parts[2]
            parts[2] = f"{depth:.3f}"
            # rebuild the line, preserving simple spacing and closing paren
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} )\n"
            print("NEW:", lines[i].strip())

        # modify the safe z height   
        elif "ZSAFE" in line and z_safe is not None:
            print("OLD:", line.strip())
            parts = line.split()
            parts[2] = f"{z_safe:.2f}"
            lines[i] = f"{parts[0]} {parts[1]}      {parts[2]} )\n"
            print("NEW:", lines[i].strip())
        
        # modify the x_origin
        elif "xorigin" in line and origin_offset is not None: 
            print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[0]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            print("NEW:", lines[i].strip())
        
        # modify the y_origin
        elif "yorigin" in line and origin_offset is not None:
            print("OLD: ", line.strip())
            parts = line.split()
            parts[2] = f"{origin_offset[1]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}    {parts[2]} )\n"
            print("NEW:", lines[i].strip())
        
        # modify the finish position 
        elif "gpost" in line and finish_position is not None: 
            print("OLD: ", line.strip())
            parts = line.split()
            post_loc = f"X{finish_position[0]:.3f} Y{finish_position[1]:.3f} Z{finish_position[2]:.3f}"
            lines[i] = f"{parts[0]} {parts[1]}       {parts[2]} {post_loc} {parts[6]} {parts[7]}  )\n"
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

# works
def generate_engraving_text(state_idx, plate_num): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]

    template_path = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{states[state_idx]}/text.txt"
    modtext_path = f"/home/pi/Documents/F-Engrave-1.76_src/output/eng_text_{datetime.now()}_{plate_num}_{states[state_idx]}.txt"

    with open(template_path, "r") as f: 
        template_lines = f.readlines()

    print("------------------------------------------------------")
    print(f"Please input the details of the {states[state_idx]} plate, and press 'Enter'. ")
    
    # NSW
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
        
        
        values = [lsc_num, date, cert_num, VIN, Eng_num, Seat_cap, front_tyre, rear_tyre, modGVM, modGCM, modGTM, modATM, modCode]
        print(values[12])
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                if i == 7: 
                    print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline
    
    # QLD plates
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
        front_tyre = str(input("Tyre Size: Front  "))
        rear_tyre = str(input("Tyre Size: Rear  "))
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
        
        
        values = [lsc_num, date, cert_num, Mod_bod, modCode, VIN, front_tyre, rear_tyre, Seat_cap, modGVM, modGCM, modGTM, modATM]
        print(values[12])
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 2: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                if i == 3: 
                    print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 5:
                    print(f"i: {i}, j: {j}, k: {k}")
                    newline = newline + space_tokens[0] + "FRONT: " + values[j] + "  REAR: " + values[j+1] + "\n"
                    # newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 2
                    modtext_lines[i] = newline  
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline

    # vic heavy plate
    elif state_idx == 2: 
        lsc_num = str(input("VASS Certificate No: "))
        date = str(input("Date (Press Enter for TODAY): ")) # can make this automatic
        if date == "": 
            today = str(datetime.now()).split()[0].split("-")  # extract the date, then split to extract y-m-d
            date = f"{today[2]}/{today[1]}/{today[0]}" # convert to d-m-y
            # print(date)
        modCode = str(input("Modification Codes (seperate with '. '): ")) # might get comma, write a function to chop it up to just seperated by fullstops
        VIN = str(input("VIN: "))
        front_tyre = str(input("Tyre Size: Front  "))
        rear_tyre = str(input("Tyre Size: Rear  "))
        Mod_axles = str(input("Modified Number of Axles: "))
        ADR_cat = str(input("ADR CAT: "))
        Seat_cap = str(input("Seating Capacity: "))
        bod_style = str(input("Body Style: "))
        modGVM = str(input("Modification GVM/ATM: "))
        modGCM = str(input("Modification GCM/GTM: "))
        ser_no = str(input("Serial Number: "))
        
        
        values = [lsc_num, date, modCode, VIN, front_tyre, 
                  rear_tyre, Mod_axles, ADR_cat, Seat_cap, bod_style, modGVM, modGCM, ser_no]
        print(values[12])
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i not in [1, 8]: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                if i == 2: 
                    print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                elif i == 4: 
                    print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + "FRONT: " + values[j] + "    REAR: " + values[j+1] + "\n"
                    j += 2
                    modtext_lines[i] = newline                    
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            elif i == 8: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                newline = stuff_tokens[0]
                newline = newline + "\n"
                modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                for k in range(len(space_tokens)-1): # exclude the \n at the end
                    newline = stuff_tokens[0] + space_tokens[k] + values[j]
                    j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline

    # VIC light plate
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
        
        
        values = [ste, date, cert_num, yr_mk_mod, VIN, Seat_cap, ADR_cat, bod_style, modCode, modGVM, modGCM, ser_no]
        modtext_lines = template_lines.copy()
        j = 0
        for i, line in enumerate(template_lines): 
            newline = ""
            if i != 1: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                if i == 4:  # line with mod codes
                    print(f"i: {i}, j: {j}, k : {k}")
                    newline = newline + space_tokens[0] + values[j] + '\n'
                    j += 1 
                    modtext_lines[i] = newline
                else: 
                    for k in range(len(space_tokens)-1): # exclude the \n at the end
                        print(f"i: {i}, j: {j}, k : {k}")
                        newline = newline + space_tokens[k] + values[j]
                        j += 1
                    newline = newline + "\n"
                    modtext_lines[i] = newline
            else: 
                space_tokens = re.findall("\s+", line)   # /s is whitespace character, + means to find all the following whitespace characters that are the same
                stuff_tokens = line.split()
                print(stuff_tokens, space_tokens)
                # exclude the \n at the end
                newline = stuff_tokens[0] + space_tokens[0] + values[j]
                j += 1
                newline = newline + "\n"
                modtext_lines[i] = newline


    with open(modtext_path, "w") as f:
         f.writelines(modtext_lines)


    # print(template_lines)


    return modtext_path, modtext_lines






if __name__=="__main__":
    # code status: all seperate code tested and working universal mapping synchronisation between calibration not yet verified
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
    

    # unlock and return to original position
    unlock(ser)  
    if sesh_config.islath:
        mapping = sesh_config.mapping_lath
    else:
        mapping = sesh_config.mapping_work

    # move to last finished work Position
    try: 
        ser = homeNcalibrate(ser, mapping, sesh_config.finish_wPos)
        print_main_menu()
    except: 
        print("Homing Failed, please ensure there are no obstructions and try again.")
        print_main_menu()



    while keyboardInput != "n":
        keyboardInput = getch().lower()
        if keyboardInput == "1": 
            unlock(ser)
            print("Machine Unlocked!")
            print_main_menu()
        if keyboardInput == "2": 
            try: 
                ser = homeNcalibrate(ser, mapping, sesh_config.wPos_home)
                print_main_menu()
            except: 
                print("Homing Failed, please ensure there are no obstructions and try again.")
                print_main_menu()
        if keyboardInput == "3": 
            try: 
                ser = verify_wPos(ser, sesh_config.mapping_work)
                print_main_menu()
            except: 
                print("Verification Failed.")
                print_main_menu()
        if keyboardInput == "4": 
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
        if keyboardInput == "5": 
            ser, mapping = zero_xy(ser)
            sesh_config.mapping_work = mapping

            with open(config_path, "w") as f:
                # convert config dataclass to dictionary 
                json.dump(asdict(sesh_config), f, indent=4)
            print_main_menu()
        if keyboardInput == "6": 
            ser, mapping = zero_z(ser)
            sesh_config.mapping_work = mapping
            with open(config_path, "w") as f:
                # convert config dataclass to dictionary 
                json.dump(asdict(sesh_config), f, indent=4)
            print_main_menu()
        if keyboardInput == "7": 
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
            write_gcode(ser, gcode_path, sesh_config.mapping_lath)

            # edit the mapping to reflect the new z height 
            sesh_config.mapping_lath = (sesh_config.mapping_lath[0], sesh_config.mapping_lath[1], sesh_config.mapping_lath[2] + abs(depth))
            sesh_config.mapping_work = (sesh_config.mapping_work[0], sesh_config.mapping_work[1], sesh_config.mapping_work[2] + abs(depth))
            with open(config_path, "w") as f:
                # convert config dataclass to dictionary 
                json.dump(asdict(sesh_config), f, indent=4)
            print_main_menu()
        if keyboardInput == "8":
            again = None
            if again != "y":
                print("---------------------------------------")
                print("1 - NSW \n2 - QLD \n3- VIC_Heavy\n4 - VIC_Light")
                state_idx =  int(input("Please select the plate type: ")) - 1
                plate_num = input("Please input plate serial number(press enter for default): ")
                if plate_num == "": 
                    plate_num = f"{sesh_config.year}_{state_idx}{(sesh_config.plate_counter[state_idx] + 1):03d}"
                    sesh_config.plate_counter = list(sesh_config.plate_counter)
                    sesh_config.plate_counter[state_idx] += 1
                    sesh_config.plate_counter = tuple(sesh_config.plate_counter)
                    print(plate_num)
                    with open(config_path, "w") as f:
                        # convert config dataclass to dictionary 
                        json.dump(asdict(sesh_config), f, indent=4)
                # make a JSON and a way to read the plate_num
                else: 
                    plate_num = int(plate_num)

                # generate the text
                try: 
                    eng_textpath, eng_textlines = generate_engraving_text(state_idx, plate_num)
                except: 
                    print("Error generating engraving text, please try again.")
                    print_main_menu()
                    continue

                # check if engraving settings need to be changed
                depth = input("Enter changes to cutting depth in mm (press Enter for default): ")
                z_safe = input("Enter new safe z height in mm (press Enter for default): ")
                origin_offset = input("Enter new origin offset as 'x,y' in mm (press Enter for default): ")
                finish_position = input("Enter new finish position as 'x,y,z' in mm (press Enter for default): ")
                if finish_position == "": 
                    finish_position = (0,125,20)
                if depth == "": 
                    depth = None
                else: 
                    depth = float(depth)
                if z_safe == "":
                    z_safe = None
                if origin_offset == "":
                    origin_offset = None




                # write the gcode
                try:
                    gcode_path, curr_config = generate_gcode(state_idx, eng_textpath, plate_num, depth=depth, z_safe=z_safe, origin_offset=origin_offset, finish_position=finish_position)
                except: 
                    print("Error generating gcode, please try again.")
                    print_main_menu()
                    continue
                write_gcode(ser, gcode_path)
                # impliment a again? function here 
                print("---------------------------------------")
                print("Engraving Complete!")
                # print(f"Current Config: \n ZSAFE:  {curr_config["ZSAFE"]} \n ZCUT: {curr_config["ZCUT"]} \n XORIGIN: {curr_config["XORIGIN"]} \n YORIGIN: {curr_config["YORIGIN"]} \n GPOST: {curr_config["GPOST"]} ")
                again = input("Please check Engraving quality. Press 'y' if satisfactory, 'n' to repeat: ").lower()

            print_main_menu()


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
    

    # port = scan_grbl_port(115200)
    # gcode_path = "108205-5.ngc"
    # if port:
    #     print("Grbl Device on port: ", port)
    #     ser = verify_wPos(send_wakeup(port=port))
    #     # seems to reset
    #     jog(ser)
        
    #     write_gcode(ser, gcode_path)
    # else: 
    #     print("no Grbl Device found")
