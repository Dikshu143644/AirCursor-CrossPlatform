"""Cross-platform unit tests for the macOS CoreGraphics event adapter."""
import unittest
from types import SimpleNamespace

from macos.driver import MacOSEventSynthesizer, MacOSDriverUnavailableError


class FakeQuartz:
    kCGHIDEventTap = 1
    kCGEventMouseMoved = 0
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGEventRightMouseDown = 3
    kCGEventRightMouseUp = 4
    kCGEventOtherMouseDown = 5
    kCGEventOtherMouseUp = 6
    kCGMouseButtonLeft = 0
    kCGMouseButtonRight = 1
    kCGMouseButtonCenter = 2
    kCGScrollEventUnitLine = 1

    def __init__(self):
        self.events = []
        self.location = SimpleNamespace(x=40.0, y=75.0)

    def CGEventCreate(self, source):
        return object()

    def CGEventGetLocation(self, event):
        return self.location

    def CGEventCreateMouseEvent(self, source, event_type, point, button):
        return {"type": event_type, "point": point, "button": button}

    def CGEventCreateScrollWheelEvent(self, source, units, wheel_count, vertical, horizontal):
        return {"type": "scroll", "vertical": vertical, "horizontal": horizontal}

    def CGEventPost(self, tap, event):
        self.events.append(event)
        if isinstance(event, dict) and event.get("type") == self.kCGEventMouseMoved:
            self.location = SimpleNamespace(x=event["point"][0], y=event["point"][1])


class MacOSDriverTests(unittest.TestCase):
    def setUp(self):
        self.quartz = FakeQuartz()
        self.driver = MacOSEventSynthesizer(quartz=self.quartz)

    def test_move_to_and_relative_move(self):
        self.driver.move_to(100, 120)
        self.assertEqual(self.quartz.events[-1]["point"], (100.0, 120.0))
        self.driver.move_relative(5, -10)
        self.assertEqual(self.quartz.events[-1]["point"], (105.0, 110.0))
        self.assertEqual(self.driver.current_location(), (105, 110))
        self.assertEqual(self.driver.get_current_location(), (105, 110))

    def test_left_right_middle_click_mapping(self):
        self.driver.click("left", 10, 20)
        self.driver.click("right", 10, 20)
        self.driver.click("middle", 10, 20)
        event_types = [event["type"] for event in self.quartz.events]
        self.assertEqual(event_types, [1, 2, 3, 4, 5, 6])

    def test_double_click_posts_two_click_pairs(self):
        self.driver.double_click(5, 6)
        self.assertEqual(len(self.quartz.events), 4)

    def test_drag_release_all_buttons(self):
        self.driver.left_down(3, 4)
        self.assertIn("left", self.driver._pressed_buttons)
        self.driver.release_all_buttons()
        self.assertNotIn("left", self.driver._pressed_buttons)
        self.assertEqual(self.quartz.events[-1]["type"], self.quartz.kCGEventLeftMouseUp)

    def test_scroll_uses_vertical_and_horizontal_deltas(self):
        self.driver.scroll(vertical=2, horizontal=-1)
        self.assertEqual(self.quartz.events[-1], {
            "type": "scroll", "vertical": 2, "horizontal": -1
        })

    def test_invalid_button_and_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            self.driver.click("sideways")
        with self.assertRaises(ValueError):
            self.driver.move_to(float("nan"), 0)
        with self.assertRaises(ValueError):
            self.driver.left_down(1, None)

    def test_missing_quartz_has_actionable_error(self):
        with self.assertRaises(MacOSDriverUnavailableError):
            MacOSEventSynthesizer(quartz=False)


if __name__ == "__main__":
    unittest.main()
