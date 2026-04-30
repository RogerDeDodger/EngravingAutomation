from flask import Flask, render_template, jsonify, request, send_file
import threading
import time
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

app = Flask(__name__)

# simulated machine state
machine_state = {
    "mx": 0,
    "my": 0,
    "mz": 0,
    "wx": 0,
    "wy": 0,
    "wz": 0
}

settings = {
    "feedrate": 1000,
    "tool": "endmill"
}


# ---------------------------
# simulate machine motion
# ---------------------------

def machine_sim():
    while True:
        machine_state["mx"] += np.random.uniform(-0.1, 0.1)
        machine_state["my"] += np.random.uniform(-0.1, 0.1)
        machine_state["mz"] += np.random.uniform(-0.05, 0.05)

        machine_state["wx"] = machine_state["mx"]
        machine_state["wy"] = machine_state["my"]
        machine_state["wz"] = machine_state["mz"]

        time.sleep(0.5)


threading.Thread(target=machine_sim, daemon=True).start()


# ---------------------------
# pages
# ---------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html", settings=settings)


# ---------------------------
# machine state API
# ---------------------------

@app.route("/machine_state")
def machine_state_api():
    return jsonify(machine_state)


# ---------------------------
# keyboard control
# ---------------------------

@app.route("/jog", methods=["POST"])
def jog():
    key = request.json["key"]

    step = 1

    if key == "w":
        machine_state["my"] += step
    elif key == "s":
        machine_state["my"] -= step
    elif key == "a":
        machine_state["mx"] -= step
    elif key == "d":
        machine_state["mx"] += step

    return "ok"


# ---------------------------
# settings validation
# ---------------------------

@app.route("/save_settings", methods=["POST"])
def save_settings():

    data = request.json

    try:
        feed = int(data["feedrate"])
        if feed < 0 or feed > 5000:
            return jsonify({"status": "error", "msg": "feedrate out of range"})
    except:
        return jsonify({"status": "error", "msg": "feedrate must be integer"})

    settings["feedrate"] = feed
    settings["tool"] = data["tool"]

    return jsonify({"status": "ok"})


# ---------------------------
# plot image endpoint
# ---------------------------

@app.route("/plot.png")
def plot_png():

    x = np.linspace(0, 10, 100)
    y = np.sin(x)

    scatter_x = np.random.rand(20)*10
    scatter_y = np.sin(scatter_x)

    fig, ax = plt.subplots()

    ax.plot(x, y)
    ax.scatter(scatter_x, scatter_y, c="red")

    ax.imshow(np.random.rand(50,50),
              extent=[0,10,-1,1],
              alpha=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()

    buf.seek(0)

    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)