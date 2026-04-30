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
previewGenerationFinished = False
previewPath = None

@app.route("/")
def home():
    return render_template("index.html")

@app.route('/load_initial_settings')
def load_initial_settings():
    # assume initial state is QLD
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


@app.route('/reload_engraver_settings', method=["POST"])
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

    state = data["state"]
    states =  ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    stateIdx = states.index(state)
    plateImg = plt.imread(f"plates_images/{states[stateIdx]}_ModPlate_Image.jpg")
    plateNum = get_plate_num(state, textData)
    eng_textpath, eng_textlines = generate_engraving_text_web(stateIdx, plateNum, textData, False)
    
    # generate the gcode
    gcode_path, curr_config = generate_gcode_web(stateIdx, eng_textpath, plateNum, engData, engDataMore)

    print("finished generating gcode, now generating preview")

    # obtain latest mapping and originOffset value
    mapping = [200.006,
        150.558,
        26.976] 
    originOffset = (0, 2)
    previewPath = generate_preview(stateIdx, gcode_path, plateNum, mapping, originOffset)

    return previewPath 

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
    app.run(host="0.0.0.0", port=5000)