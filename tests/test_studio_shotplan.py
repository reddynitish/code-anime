import unittest

from studio.shotplan import default_bedroom_plan, total_duration


class ShotPlanTests(unittest.TestCase):
    def test_explicit_three_shots_summing_to_ten_seconds(self):
        shots = default_bedroom_plan()
        self.assertEqual([s.duration for s in shots], [3.0, 4.0, 3.0])
        self.assertEqual(total_duration(shots), 10.0)

    def test_shots_are_in_order_and_contiguous(self):
        shots = default_bedroom_plan()
        self.assertEqual(shots[0].start, 0.0)
        for prev, nxt in zip(shots, shots[1:]):
            self.assertEqual(prev.end, nxt.start)
        self.assertEqual(shots[-1].end, 10.0)

    def test_plan_is_deterministic(self):
        a = default_bedroom_plan()
        b = default_bedroom_plan()
        self.assertEqual([s.prompt for s in a], [s.prompt for s in b])
        self.assertEqual([s.description for s in a], [s.description for s in b])

    def test_prompts_preserve_style_identity_and_room(self):
        for shot in default_bedroom_plan():
            self.assertIn("reference image", shot.prompt)
            self.assertIn("character design", shot.prompt)
            self.assertIn("bedroom", shot.prompt.lower() + shot.description.lower())

    def test_custom_scene_text_honored(self):
        shots = default_bedroom_plan(scene="opening the closet door slowly")
        self.assertEqual(len(shots), 3)
        self.assertEqual(total_duration(shots), 10.0)
        for s in shots:
            self.assertIn("opening the closet door slowly", s.prompt)


if __name__ == "__main__":
    unittest.main()

