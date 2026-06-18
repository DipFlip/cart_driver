# Cart Driver

Browser-based WASD controller for a two-motor RobStride cart:

- Motor 1: steering, with startup position captured as straight
- Motor 2: rear-wheel velocity control
- Official RobStride CH340/GD32 USB-CAN adapter on `/dev/ttyUSB0`

## Safety behavior

- Motors must be explicitly connected and armed.
- W/S is dead-man drive control; releasing the key/button commands zero speed.
- A/D slews steering within ±60° and holds the resulting angle.
- A 350 ms browser-command watchdog stops drive and steering slew.
- STOP/disarm and server shutdown command zero drive speed and disable both motors.
- Drive uses damped MIT velocity control with a 200°/s² command ramp.
- Drive torque is limited to 2 Nm and speed to 100°/s by default.

## Install and run

```bash
cd ~/repos/cart_driver
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Open `http://<raspberry-pi-ip>:5000/`.

Set a different adapter path if needed:

```bash
ROBSTRIDE_PORT=/dev/ttyUSB1 .venv/bin/python app.py
```

Keep the cart lifted or otherwise restrained during initial testing.

## Run as a service

```bash
sudo install -m 0644 cart-driver.service /etc/systemd/system/cart-driver.service
sudo systemctl daemon-reload
sudo systemctl enable --now cart-driver.service
```

Inspect logs with:

```bash
journalctl -u cart-driver.service -f
```
