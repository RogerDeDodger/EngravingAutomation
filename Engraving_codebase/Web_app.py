from flask import Flask, render_template, jsonify, request
import subprocess
import threading
from matplotlib import pyplot as plt
import os
from Engraving_codebase import *
import numpy as np
app = Flask(__name__)
import time


# startup script to define global variables
statuses = ["IDLE", "PROCESSING", "ENGRAVING", "MOVING", "ERROR", "HOMING"]
config_path = "/home/pi/Documents/Engraving_codebase/script_config.json"
previewGenerationFinished = False
previewPath = None
status = statuses[0]
mStarted = False
ser = None
mapping = None
sesh_config = None
spindle_on_bool = False
serialLock = threading.Lock()
spdIdx = 2

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/poll-Mstatus", methods=["GET"])
def pollStatus(): 
    # declare global and ensure changes stay
    global mStarted
    global ser
    global mapping

    if not mStarted: 
        mStarted = True
        ser = send_wakeup()

        global config_path
        global sesh_config
        with open(config_path, "r") as f: 
            config_dict = json.load(f)
            sesh_config = config(**config_dict)

        # load in the mapping
        mapping = sesh_config.mapping_work

        with serialLock: 
            ser = homeNcalibrate(ser, mapping, sesh_config.finish_wPos)

        mStarted = True
        # initiate auto starting sequence - catch for startup sequence, load in config file

    elif not ser.is_open: 
        port = scan_grbl_port(115200)
        ser = send_wakeup(port=port)
        # restart starting sequence to zero and map

    with serialLock: 
        ser.reset_input_buffer()
        ser.write(b"?")
        time.sleep(0.5)
        response = ser.read_until(b'>').decode()

    print(response)
    while True: 
        if response.find('Grbl 0.9j') == -1: 
            try: 
                status = response[response.index("<")+1:response.index(",M")]
            except: 
                time.sleep(1)
                continue

            statuses = ["idle", "run", "home", "alarm", 'hold']
            statusIdx = statuses.index(status.lower())
            colors = ["#4F7942", "#6495ED", "#7B4000", "#FF1540", "#FF5F15"] # #FF5F15 is hex code for safety orange
            # [idle, Run, Home, Alarm]

            if statusIdx == -1:
                colors = "black"
            print(colors[statusIdx])
            return jsonify({"Mstatus": status, 
                            "color": colors[statusIdx]})
        else: 
            with serialLock: 
                ser.write(b"?")
                time.sleep(0.5)
                response = ser.read_until(b'>').decode()
        





@app.route("/unlock", methods=["GET"])
def unlockMachine(): 
    with serialLock: 
        unlock(ser)
    return "ok"


@app.route("/estop", methods=["GET"])
def softStop(): 
    with serialLock: 
        # FLAG, may have small delay will fix redundancy later
        ser.write(b"!")
        time.sleep(0.5)
    return "ok"

@app.route("/jogManualStep", methods=["POST"])
def jogManualStep(): 
    global ser # have to assume ser is connected cause this needs to move fast without delays
    global spindle_on_bool
    
    data = request.get_json()
    print("received data:", data)
    speed = float(data['speed'])
    direciton = data['direction']
    ser, spindle_on_bool = jog_web(ser, speed, direciton, spindle_on_bool)

    return "ok"

@app.route("/jogAutoStep", methods=['POST'])
def jogAutoStep():
    '''
    
    identical as jog manual step, but now with discrete speed control. 
    
    '''
    global ser
    global spindle_on_bool
    global spdIdx
    data = request.get_data(as_text=True)
    speeds = [0.01, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50]
    print(data)
    if data == "spd":
        spdIdx = spdIdx + 1
        return jsonify({"speed": speeds[spdIdx]})
    elif data == "start": 
        spdIdx = 2
        return "ok"
    else: 
        with serialLock: 
            ser, spindle_on_bool = jog_web(ser, speeds[spdIdx], data, spindle_on_bool)
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
    return "ok"


@app.route("/zeroworkingCoords", methods=["GET"])
def zeroWorkingCoords(): 
    '''
    
    Zero the working cordinates, update the mapping and save the mapping to default of save as defalt origin is pressed

    '''
    global sesh_config
    data = request.get_json()
    print("revieved data: ", data)

    if data["type"] != "save": 
        # poll for mapping, zero then save to sesh config
        with serialLock: 
            # obtain current mapping = work - machine
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            ser.write(b"?")
            time.sleep(0.5)
            string = ser.read_until(b'>').decode()
            MPos = string[string.index("M")+5:string.index("W")-1]
            MPos = tuple(float(i) for i in MPos.split(","))

            WPos = string[int(string.index("W")+5):string.index(">")]
            WPos = tuple(float(i) for i in WPos.split(","))
            if data["type"] == "XY": 
                WPos = (0, 0, WPos[2])
            elif data["type"] == "Z": 
                WPos = (WPos[0], WPos[1], 0)
            if data["tab"] == "Calibrate": 
                sesh_config.mapping_lath = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
            elif data["tab"] == "Prepare": 
                sesh_config.mapping_work = (WPos[0] - MPos[0], WPos[1] - MPos[1], WPos[2] - MPos[2])
    else: 
        with open(config_path, "w") as f: 
            # save to config_path file, otherwise the mapping is temporarily used during the session
            json.dump(asdict(sesh_config), f, indent=4)

    return "ok"









@app.route("/getMapping", methods=["GET"])
def getMapping(): 
    print(mapping)
    return jsonify({"x": mapping[0], 
                    "y": mapping[1], 
                    "z": mapping[2]})
        

@app.route("/manualJog", methods=["POST"])
def manualJog():
    # prefer to work in absolute machine cordinate for debugging purposes
    data = request.get_json()
    print("recieved data: ", data) # FLAG remove later

    if data["method"] == "Work": 
        # convert to machine using mapping, machine = work - mapping
        mPosX = float(data["x"]) - mapping[0]
        mPosY = float(data["y"]) - mapping[1]
        mPosZ = float(data["z"]) - mapping[2]
    else: 
        mPosX = float(data["x"])
        mPosY = float(data["y"]) # FLAG STILL DEBUGGING KEY ERRORS AND ECT
        mPosZ = float(data["z"])

    cmd = f"G53 X{mPosX:.3f} Y{mPosY:.3f} Z{mPosZ:.3f}\n"
    ser.write(str.encode(cmd))
    wait_for_movement_completion(ser, cmd)

@app.route("/pollPoses", methods=["GET"])
def pollPoses(): 
    # poll ser and wait for response
    with serialLock: 
        ser.write(b"?")
        string = ser.read_until(b'>').decode()   # this reads the closes 100 bytes, most likely performance error
        print(string)
    if string.find("WPos") != -1 and string.find("MPos") != -1: 
        MPos = string[string.index("M")+5:string.index("W")-1]
        MPos = tuple(float(i) for i in MPos.split(","))

        WPos = string[int(string.index("W")+5):string.index(">")]
        WPos = tuple(float(i) for i in WPos.split(","))
        print(MPos)
        print(WPos)
        return jsonify({"mPosX": float(MPos[0]), 
                        "mPosY": float(MPos[1]), 
                        "mPosZ": float(MPos[2]),
                        "wPosX": float(WPos[0]), 
                        "wPosY": float(WPos[1]),
                        "wPosZ": float(WPos[2])
        })
    else: 
        return jsonify({"mPosX": 0, 
                        "mPosY": 0, 
                        "mPosZ": 0,
                        "wPosX": 0, 
                        "wPosY": 0,
                        "wPosZ": 0
        })



@app.route("/saveDefaultSettings", methods=["POST"])
def saveDefaultSettings(): 
    states =  ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    data = request.get_json()
    print("received data:", data) # FLAG remove later

    engData = data['engravingSettings']
    engDataMore = data['engravingSettingsMore']

    state = data["state"]
    stateIdx = states.index(state)
    
    # generate the gcode
    save_default_settings(stateIdx, engData, engDataMore)
    return "OK"


@app.route('/reload_engraver_settings', methods=["POST"])
def reload_engraver_settings():
    # assume initial state is QLD
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    state = request.data.decode("utf-8") # data is stored in bytes
    if state not in states: 
        state = "QLD"
    # defaultTextPath = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{state}/text_default.txt"
    defaultSettingsPath = f"/home/pi/Documents/F-Engrave-1.76_src/configuration/{state}/settings_default.txt"

    with open(defaultSettingsPath, 'r') as f:
        settingslines = f.readlines()
    settings = {}
    for line in settingslines:
        if line.find("ZCUT") != -1: 
            values = line.split()
            settings.update({"cutZ": values[2]})
        elif line.find("ZSAFE") != -1:
            values = line.split()
            settings.update({"safeZ": values[2]})
        elif line.find("xorigin") != -1:
            values = line.split()
            settings.update({"originX": values[2]})
        elif line.find("yorigin") != -1:
            values = line.split()
            settings.update({"originY": values[2]}) 
        # the gpost and gpre contain post and precodes           
        elif line.find("gpost") != -1:
            values = line.split()

            settings.update({"finalX": values[3][1:]})
            settings.update({"finalY": values[4][1:]})
            settings.update({"finalZ": values[5][1:]})
            gPostStr = values[6]
            for i in range(7, len(values) -1): 
                gPostStr = gPostStr + " " + values[i]
            settings.update({"gPost": gPostStr})
            
        elif line.find("gpre") != -1:
            values = line.split()
            gPreStr = values[2]
            for i in range(3, len(values) -1): 
                gPreStr = gPreStr + " " + values[i]
            
            settings.update({"gPre": gPreStr})
            
        elif line.find("FEED") != -1: 
            values = line.split() 
            settings.update({"feedRate": values[2]})
        elif line.find("PLUNGE") != -1:
            values = line.split()
            settings.update({"plungeRate": values[2]})
        elif line.find("YSCALE") != -1: 
            # textheight
            values = line.split()
            print(values)
            settings.update({"textHeight": values[2]})
        elif line.find("STHICK") != -1: 
            values = line.split()
            settings.update({"lineThickness": values[2]})
        elif line.find("XSCALE") != -1: 
            values = line.split()
            settings.update({"textWidth": values[2]})
        elif line.find("CSPACE") != -1: 
            values = line.split()
            settings.update({"charSpacing": values[2]})
        elif line.find("WSPACE") != -1: 
            values = line.split()
            settings.update({"wordSpacing": values[2]})
        elif line.find("LSPACE") != -1: 
            values = line.split()
            settings.update({"lineSpacing": values[2]})
        elif line.find("TANGLE") != -1: 
            values = line.split()
            settings.update({"textAngle": values[2]})

    # export the dictionary as a json
    print(settings)
    return jsonify(settings) # converts to a json string as all data transmitted must be strings

@app.route('/send_settings', methods=['POST']) # post means it will recieve data from the frontend
def send_settings(): 
    # get the data and process it
    data = request.get_json()
    print("received data:", data)
    global textData 
    textData = data['textInput']
    engData = data['engravingSettings']
    engDataMore = data['engravingSettingsMore']

    # convert date
    htmlDateFormat = textData["date"] # "YYYY-MM_DD"
    dates = htmlDateFormat.split("-")
    ausDateFormat = f"{dates[2]}/{dates[1]}/{dates[0]}"
    textData["date"] = ausDateFormat
    state = data["state"]
    states =  ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    stateIdx = states.index(state)
    plateImg = plt.imread(f"plates_images/{states[stateIdx]}_ModPlate_Image.jpg")
    plateNum = get_plate_num(state, textData)
    del textData['plateSerialNumber']# remove first line from textData FLAG
    eng_textpath, eng_textlines = generate_engraving_text_web(stateIdx, plateNum, textData, False)
    
    # generate the gcode
    gcode_path, curr_config = generate_gcode_web(stateIdx, eng_textpath, plateNum, engData, engDataMore)

    print("finished generating gcode, now generating preview")

    # use current mapping
    previewPath = generate_preview(stateIdx, gcode_path, plateNum, mapping)

    if data['print'] == 'yes': 
        with serialLock: 
            timeEst, spindle_travel, spindle_stops = estimate_time(ser, gcode_path) 
        
        return jsonify({"timeEst": timeEst, 
                        "gcodePath": gcode_path, 
                        "spindle_travel": spindle_travel, 
                        "spindle_stops": spindle_stops})
    return previewPath 

@app.route('/start_engraving', methods=["POST"])
def start_engraving(): 
    data = request.get_json()
    # FLAG
    print("recieved data: ", data)
    with serialLock: 
        write_gcode(ser, data["gcode"], spindle_travel=data["x"], spindle_stops=data["u"], verbose=False)
    
    return "Ok"

# load default settings for the engraving job, or the last settings used, and send them to the frontend
@app.route('/get_settings', methods=['GET'])  # these app route are named by you GET means no input needed
def get_settings():
    return jsonify({"safeZ": 5, 
                    "cutZ": -1, 
                    "feedrate": 1000, 
                    "originX": 0, 
                    "originY": 0, 
                    "finishX": 100, 
                    "finishY": 100})

# @app.route('/generatePreview', methods=['GET'])
# def generatePreview():
#     global previewGenerationFinished
#     # Wait for preview to be generated
#     while not previewGenerationFinished:
#         time.sleep(0.1)  # short sleep to avoid busy waiting
#     # Reset the flag
#     previewGenerationFinished = False
#     print(f"Returning preview URL: /{previewPath}")
#     return jsonify({"preview_url": f"/{previewPath}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)