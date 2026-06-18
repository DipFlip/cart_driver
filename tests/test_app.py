import math

from app import create_app
from cart_controller import CartController


class FakeController:
    def __init__(self):
        self.controls = None
        self.data = {
            "connected": False,
            "armed": False,
            "error": None,
            "steering_deg": 0.0,
            "steering_target_deg": 0.0,
            "drive_speed_deg_s": 0.0,
            "drive_target_deg_s": 0.0,
            "drive_temperature_c": None,
            "steering_temperature_c": None,
            "last_command_age_ms": None,
        }

    def status(self):
        return self.data.copy()

    def connect(self):
        self.data["connected"] = True

    def arm(self):
        self.data["armed"] = True

    def disarm(self):
        self.data["armed"] = False

    def center_steering(self):
        self.data["steering_target_deg"] = 0.0

    def set_center_here(self):
        self.data["steering_deg"] = 0.0
        self.data["steering_target_deg"] = 0.0

    def set_controls(self, drive_direction, steering_input, speed_deg_s):
        self.controls = (drive_direction, steering_input, speed_deg_s)


def test_control_api():
    controller = FakeController()
    client = create_app(controller).test_client()

    assert client.post("/api/connect").get_json()["connected"]
    assert client.post("/api/arm").get_json()["armed"]
    response = client.post(
        "/api/control", json={"drive": 1, "steer": -1, "speed": 75}
    )
    assert response.status_code == 200
    assert controller.controls == (1, -1, 75)
    assert client.post("/api/set-center").status_code == 200
    assert not client.post("/api/disarm").get_json()["armed"]


def test_controller_speed_defaults():
    controller = CartController()
    assert controller.max_drive_speed_deg_s == 500.0
    assert controller.steering_gear_ratio == 2.0
    assert controller.steering_rate_deg_s == 225.0
    assert controller.steering_acceleration_deg_s2 == 4_500.0
    assert controller.steering_center_rate_deg_s == 30.0
    assert controller.drive_acceleration_deg_s2 == 1_000.0


def test_idle_control_profiles():
    controller = CartController()

    controller._steering_target_deg = 10.0
    controller._steering_feedback_deg = 9.5
    assert controller._steering_gains() == (0.0, 0.0)

    controller._steering_feedback_deg = 8.0
    assert controller._steering_gains() == (3.0, 0.2)

    controller._steering_input = 1
    assert controller._steering_gains() == (8.0, 0.8)

    controller._drive_direction = 0
    controller._drive_command_deg_s = 0.0
    assert controller._drive_damping() == 0.0

    controller._drive_command_deg_s = 10.0
    assert controller._drive_damping() == 1.0


def test_steering_gear_ratio_and_center_capture():
    controller = CartController()
    controller._straight_position_rad = 1.0

    motor_position = controller._vehicle_angle_to_motor_position(10.0)
    assert math.isclose(motor_position, 1.0 - math.radians(20.0))
    assert math.isclose(
        controller._motor_position_to_vehicle_angle(motor_position), 10.0
    )

    controller._status.armed = True
    controller._steering_position_rad = 1.25
    controller._steering_target_deg = 20.0
    controller._steering_feedback_deg = 18.0
    controller.set_center_here()
    assert controller._straight_position_rad == 1.25
    assert controller._steering_target_deg == 0.0
    assert controller._steering_feedback_deg == 0.0
