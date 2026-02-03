from Engraving_codebase import * 
import json
from dataclasses import asdict, dataclass, is_dataclass

if __name__ == "__main__":
    
    # generate_gcode(0, "hi", 3, -0.050,4)
    config_test = config()
    filename = "/home/pi/Documents/Engraving_codebase/script_config.json"
    
    # dumping config dataclass to json file
    with open(filename, "w") as f: 
        # convert config dataclass to dictionary 
        config_dict = asdict(config_test)
        json.dump(config_dict, f, indent=4)

    # loading config dataclass from json file
    with open(filename, "r") as f:
        config_dict = json.load(f)
        config_loaded = config(**config_dict)  # unpacking dictionary to config dataclass
        
    print(config_loaded.notes)
    print(str(datetime.now().year)[2:])