"""Flask web application for controlling the RobStride cart."""

from __future__ import annotations

import atexit
import os

from flask import Flask, jsonify, render_template, request

from cart_controller import CartController


def create_app(controller: CartController | None = None) -> Flask:
    app = Flask(__name__)
    cart = controller or CartController(
        channel=os.environ.get("ROBSTRIDE_PORT", "/dev/ttyUSB0")
    )
    app.config["CART_CONTROLLER"] = cart

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(cart.status())

    @app.post("/api/connect")
    def connect():
        try:
            cart.connect()
            return jsonify(cart.status())
        except Exception as exc:
            status = cart.status()
            status["error"] = str(exc)
            return jsonify(status), 500

    @app.post("/api/arm")
    def arm():
        try:
            cart.arm()
            return jsonify(cart.status())
        except Exception as exc:
            status = cart.status()
            status["error"] = str(exc)
            return jsonify(status), 500

    @app.post("/api/disarm")
    def disarm():
        cart.disarm()
        return jsonify(cart.status())

    @app.post("/api/control")
    def control():
        payload = request.get_json(force=True)
        cart.set_controls(
            drive_direction=payload.get("drive", 0),
            steering_input=payload.get("steer", 0),
            speed_deg_s=payload.get("speed", 0),
        )
        return jsonify(cart.status())

    @app.post("/api/center")
    def center():
        cart.center_steering()
        return jsonify(cart.status())

    @app.post("/api/set-center")
    def set_center():
        try:
            cart.set_center_here()
            return jsonify(cart.status())
        except Exception as exc:
            status = cart.status()
            status["error"] = str(exc)
            return jsonify(status), 400

    if controller is None:
        atexit.register(cart.close)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)
