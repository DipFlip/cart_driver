"""Threaded hardware controller for a RobStride steering and drive motor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import threading
import time

from robstride_dynamics import Motor, ParameterType, RobstrideBus


@dataclass
class CartStatus:
    connected: bool = False
    armed: bool = False
    error: str | None = None
    steering_deg: float = 0.0
    steering_target_deg: float = 0.0
    drive_speed_deg_s: float = 0.0
    drive_target_deg_s: float = 0.0
    drive_temperature_c: float | None = None
    steering_temperature_c: float | None = None
    last_command_age_ms: int | None = None


class CartController:
    STEERING_NAME = "steering"
    DRIVE_NAME = "drive"

    def __init__(
        self,
        channel: str = "/dev/ttyUSB0",
        steering_id: int = 1,
        drive_id: int = 2,
        steering_limit_deg: float = 60.0,
        steering_rate_deg_s: float = 45.0,
        max_drive_speed_deg_s: float = 100.0,
        drive_acceleration_deg_s2: float = 200.0,
        drive_kd: float = 1.0,
        torque_limit_nm: float = 2.0,
        watchdog_seconds: float = 0.35,
    ):
        self.channel = channel
        self.steering_limit_deg = steering_limit_deg
        self.steering_rate_deg_s = steering_rate_deg_s
        self.max_drive_speed_deg_s = max_drive_speed_deg_s
        self.drive_acceleration_deg_s2 = drive_acceleration_deg_s2
        self.drive_kd = drive_kd
        self.torque_limit_nm = torque_limit_nm
        self.watchdog_seconds = watchdog_seconds

        motors = {
            self.STEERING_NAME: Motor(steering_id, "rs-05"),
            self.DRIVE_NAME: Motor(drive_id, "rs-05"),
        }
        calibration = {
            self.STEERING_NAME: {"direction": 1, "homing_offset": 0.0},
            self.DRIVE_NAME: {"direction": 1, "homing_offset": 0.0},
        }
        self.bus = RobstrideBus(
            channel,
            motors,
            calibration,
            bitrate=1_000_000,
            interface="robstride_serial",
            interface_kwargs={"baudrate": 921_600, "timeout": 0.02},
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = CartStatus()
        self._straight_position_rad = 0.0
        self._steering_target_deg = 0.0
        self._steering_input = 0
        self._drive_direction = 0
        self._drive_speed_setting_deg_s = max_drive_speed_deg_s
        self._drive_command_deg_s = 0.0
        self._last_command_at = 0.0

    def connect(self) -> None:
        with self._lock:
            if self._status.connected:
                return
            self.bus.connect(handshake=False)
            try:
                for name in (self.STEERING_NAME, self.DRIVE_NAME):
                    if self.bus.read_id(name, timeout=0.3) is None:
                        motor_id = self.bus.motors[name].id
                        raise RuntimeError(f"Motor ID {motor_id} did not respond")
            except Exception:
                self.bus.disconnect(disable_torque=False)
                raise

            self._status.connected = True
            self._status.error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._control_loop, name="cart-control", daemon=True
            )
            self._thread.start()

    def arm(self) -> None:
        with self._lock:
            if not self._status.connected:
                raise RuntimeError("Controller is not connected")
            if self._status.armed:
                return

            enabled: list[str] = []
            try:
                self.bus.write(self.STEERING_NAME, ParameterType.MODE, 0)
                self.bus.write(
                    self.STEERING_NAME,
                    ParameterType.TORQUE_LIMIT,
                    self.torque_limit_nm,
                )
                steering_position, _, _, steering_temp = self.bus.enable(
                    self.STEERING_NAME
                )
                enabled.append(self.STEERING_NAME)
                self._straight_position_rad = steering_position
                self._steering_target_deg = 0.0
                self.bus.write_operation_frame(
                    self.STEERING_NAME,
                    self._straight_position_rad,
                    15.0,
                    0.3,
                    0.0,
                    0.0,
                )
                self.bus.read_operation_frame(self.STEERING_NAME)

                # MIT mode with Kp=0 uses the velocity target and Kd as a
                # direct, damped velocity loop. This is smoother on RS-05 than
                # the parameter-based Mode 2 loop with generic PI gains.
                self.bus.write(self.DRIVE_NAME, ParameterType.MODE, 0)
                self.bus.write(
                    self.DRIVE_NAME,
                    ParameterType.TORQUE_LIMIT,
                    self.torque_limit_nm,
                )
                drive_position, _, _, drive_temp = self.bus.enable(self.DRIVE_NAME)
                enabled.append(self.DRIVE_NAME)
                self.bus.write_operation_frame(
                    self.DRIVE_NAME,
                    drive_position,
                    0.0,
                    self.drive_kd,
                    0.0,
                    0.0,
                )
                self.bus.read_operation_frame(self.DRIVE_NAME)

                now = time.monotonic()
                self._drive_direction = 0
                self._drive_command_deg_s = 0.0
                self._steering_input = 0
                self._last_command_at = now
                self._status.armed = True
                self._status.steering_deg = 0.0
                self._status.steering_target_deg = 0.0
                self._status.drive_speed_deg_s = 0.0
                self._status.drive_target_deg_s = 0.0
                self._status.steering_temperature_c = steering_temp
                self._status.drive_temperature_c = drive_temp
                self._status.error = None
            except Exception:
                for name in reversed(enabled):
                    try:
                        self.bus.disable(name)
                    except Exception:
                        pass
                raise

    def disarm(self) -> None:
        with self._lock:
            self._disarm_locked()

    def _disarm_locked(self) -> None:
        self._drive_direction = 0
        self._steering_input = 0
        if not self._status.connected:
            self._status.armed = False
            return
        if self._status.armed:
            try:
                self.bus.write_operation_frame(
                    self.DRIVE_NAME, 0.0, 0.0, self.drive_kd, 0.0, 0.0
                )
                self.bus.read_operation_frame(self.DRIVE_NAME)
            except Exception:
                pass
            for name in (self.DRIVE_NAME, self.STEERING_NAME):
                try:
                    self.bus.disable(name)
                except Exception:
                    pass
        self._status.armed = False
        self._status.drive_speed_deg_s = 0.0
        self._status.drive_target_deg_s = 0.0
        self._drive_command_deg_s = 0.0

    def set_controls(
        self,
        drive_direction: int,
        steering_input: int,
        speed_deg_s: float,
    ) -> None:
        with self._lock:
            self._drive_direction = max(-1, min(1, int(drive_direction)))
            self._steering_input = max(-1, min(1, int(steering_input)))
            self._drive_speed_setting_deg_s = max(
                0.0, min(self.max_drive_speed_deg_s, float(speed_deg_s))
            )
            self._last_command_at = time.monotonic()

    def center_steering(self) -> None:
        with self._lock:
            self._steering_input = 0
            self._steering_target_deg = 0.0
            self._last_command_at = time.monotonic()

    def status(self) -> dict:
        with self._lock:
            if self._last_command_at:
                self._status.last_command_age_ms = round(
                    (time.monotonic() - self._last_command_at) * 1000
                )
            return asdict(self._status)

    def close(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        with self._lock:
            self._disarm_locked()
            if self.bus.is_connected:
                self.bus.disconnect(disable_torque=False)
            self._status.connected = False

    def _control_loop(self) -> None:
        period = 0.02
        last_tick = time.monotonic()

        while not self._stop_event.wait(period):
            now = time.monotonic()
            dt = min(0.1, now - last_tick)
            last_tick = now

            with self._lock:
                if not self._status.armed:
                    continue
                try:
                    command_age = now - self._last_command_at
                    if command_age > self.watchdog_seconds:
                        self._drive_direction = 0
                        self._steering_input = 0

                    self._steering_target_deg += (
                        self._steering_input * self.steering_rate_deg_s * dt
                    )
                    self._steering_target_deg = max(
                        -self.steering_limit_deg,
                        min(self.steering_limit_deg, self._steering_target_deg),
                    )
                    steering_target_rad = self._straight_position_rad + math.radians(
                        self._steering_target_deg
                    )
                    self.bus.write_operation_frame(
                        self.STEERING_NAME,
                        steering_target_rad,
                        15.0,
                        0.3,
                        0.0,
                        0.0,
                    )
                    steering_position, _, _, steering_temp = (
                        self.bus.read_operation_frame(self.STEERING_NAME)
                    )

                    requested_drive_deg_s = (
                        self._drive_direction * self._drive_speed_setting_deg_s
                    )
                    max_drive_step = self.drive_acceleration_deg_s2 * dt
                    drive_error = requested_drive_deg_s - self._drive_command_deg_s
                    self._drive_command_deg_s += max(
                        -max_drive_step, min(max_drive_step, drive_error)
                    )
                    self.bus.write_operation_frame(
                        self.DRIVE_NAME,
                        0.0,
                        0.0,
                        self.drive_kd,
                        math.radians(self._drive_command_deg_s),
                        0.0,
                    )
                    drive_status = self.bus.read_operation_frame(self.DRIVE_NAME)

                    self._status.steering_deg = math.degrees(
                        steering_position - self._straight_position_rad
                    )
                    self._status.steering_target_deg = self._steering_target_deg
                    self._status.drive_speed_deg_s = math.degrees(drive_status[1])
                    self._status.drive_target_deg_s = requested_drive_deg_s
                    self._status.steering_temperature_c = steering_temp
                    self._status.drive_temperature_c = drive_status[3]
                    self._status.last_command_age_ms = round(command_age * 1000)
                    self._status.error = None
                except Exception as exc:
                    self._status.error = str(exc)
                    self._disarm_locked()
