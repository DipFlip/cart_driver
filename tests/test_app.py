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
    assert not client.post("/api/disarm").get_json()["armed"]


def test_controller_speed_defaults():
    controller = CartController()
    assert controller.max_drive_speed_deg_s == 500.0
    assert controller.steering_rate_deg_s == 225.0
    assert controller.steering_center_rate_deg_s == 30.0
