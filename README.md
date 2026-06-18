# Cart Driver

Browser-based WASD controller for a two-motor RobStride cart:

- Motor 1: steering, with startup position captured as straight
- Motor 2: rear-wheel velocity control
- Official RobStride CH340/GD32 USB-CAN adapter on `/dev/ttyUSB0`
- Steering uses a 2:1 motor-to-vehicle ratio: 2° motor rotation equals 1° steering.

## Safety behavior

- Motors must be explicitly connected and armed.
- W/S is dead-man drive control; releasing the key/button commands zero speed.
- A/D slews vehicle steering at up to 225°/s within ±60°.
- Manual steering uses a 2,250°/s² vehicle-side acceleration profile.
- **Set center here** records the current motor-1 position as vehicle-straight.
- Steering response is governed by speed, acceleration, and the ±60° range.
- Center steering returns separately at up to 30°/s with a gentle acceleration.
- Idle steering drops to Kp=3/Kd=0.2 and releases corrective torque inside a 0.75° deadband.
- Idle drive uses Kp=0/Kd=0 after its speed command reaches zero.
- A 350 ms browser-command watchdog stops drive and steering slew.
- STOP/disarm and server shutdown command zero drive speed and disable both motors.
- Drive uses damped MIT velocity control with a 1,000°/s² command ramp.
- Drive torque is limited to 2 Nm and speed to 500°/s.
- The drive-speed slider defaults to 250°/s.

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
