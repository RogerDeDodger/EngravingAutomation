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
import cv2
import matplotlib.pyplot as plt

# written by Roger Luo - dec 2025 
# functions to aid in display and presentation of engraving text for visual aid

folder_dir = "/home/pi/Documents/Engraving_codebase/plates_images"  # directory of the codebase folder

def display_text(state_idx, modtextLines): 
    states = ["NSW", "QLD", "VIC_Heavy", "VIC_Light"]
    state = states[state_idx]
    plate_image_path = os.path.join(folder_dir, f"{state}_ModPlate_Image.png")
    plate_image = cv2.cvtColor(cv2.imread(plate_image_path), cv2.COLOR_BGR2RGB)

    plt.imshow(plate_image)

if __name__ == "__main__": 
    display_text(0, ["Hello World!", "This is a test."])

