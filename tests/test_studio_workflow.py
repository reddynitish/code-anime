import json
import tempfile
import unittest
from pathlib import Path

from studio.workflow import WorkflowError, inject_inputs, load_workflow, validate_workflow
from tests.fixtures.backend import make_fixture_backend

FIXTURE = Path(__file__).parent / "fixtures" / "fake_anisora_workflow.json"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.backend = make_fixture_backend()

    def test_load_missing_file_raises(self):
        with self.assertRaises(WorkflowError):
            load_workflow(Path("/nonexistent/workflow.json"))

    def test_load_invalid_json_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            f.write("{not valid json")
            path = Path(f.name)
        try:
            with self.assertRaises(WorkflowError):
                load_workflow(path)
        finally:
            path.unlink()

    def test_valid_fixture_passes_validation(self):
        graph = load_workflow(FIXTURE)
        validate_workflow(graph, self.backend)  # should not raise

    def test_missing_node_id_fails_validation(self):
        graph = load_workflow(FIXTURE)
        del graph[self.backend.image_node_id]
        with self.assertRaises(WorkflowError):
            validate_workflow(graph, self.backend)

    def test_wrong_class_type_fails_validation(self):
        graph = load_workflow(FIXTURE)
        graph[self.backend.output_node_id]["class_type"] = "SaveImage"
        with self.assertRaises(WorkflowError):
            validate_workflow(graph, self.backend)

    def test_inject_inputs_does_not_mutate_original(self):
        graph = load_workflow(FIXTURE)
        original = json.dumps(graph, sort_keys=True)
        injected = inject_inputs(graph, self.backend, "uploaded.png", "a positive prompt", "a negative prompt")

        self.assertEqual(json.dumps(graph, sort_keys=True), original)
        self.assertEqual(injected[self.backend.image_node_id]["inputs"]["image"], "uploaded.png")
        self.assertEqual(
            injected[self.backend.positive_prompt_node_id]["inputs"]["text"], "a positive prompt"
        )
        self.assertEqual(
            injected[self.backend.negative_prompt_node_id]["inputs"]["text"], "a negative prompt"
        )

    def test_quantize_frame_count(self):
        from studio.workflow import quantize_frame_count

        # LTX: 8n + 1
        self.assertEqual(quantize_frame_count(72, backend_key="ltx"), 73)
        self.assertEqual(quantize_frame_count(96, backend_key="ltx"), 97)
        # Wan: 4n + 1
        self.assertEqual(quantize_frame_count(48, backend_key="wan2.2"), 49)
        self.assertEqual(quantize_frame_count(72, backend_key="wan2.2"), 73)

    def test_inject_inputs_wan_duration_and_smoke(self):
        wan_workflow_path = Path(__file__).parents[1] / "runtime" / "workflows" / "wan22_i2v.json"
        if not wan_workflow_path.is_file():
            return
        from studio.catalog import Backend
        wan_backend = Backend(
            key="wan2.2",
            name="Wan2.2",
            kind="local_comfyui",
            enabled=True,
            image_node_id="56",
            positive_prompt_node_id="6",
            negative_prompt_node_id="7",
            output_node_id="58",
        )
        graph = load_workflow(wan_workflow_path)
        injected = inject_inputs(
            graph,
            wan_backend,
            "seed.png",
            "pos prompt",
            "neg prompt",
            duration=3.0,
            fps=24,
            smoke=True,
        )
        # node 55 is Wan22ImageToVideoLatent
        self.assertEqual(injected["55"]["inputs"]["length"], 73)
        self.assertEqual(injected["55"]["inputs"]["width"], 640)
        self.assertEqual(injected["55"]["inputs"]["height"], 360)
        # node 3 is KSampler
        self.assertEqual(injected["3"]["inputs"]["steps"], 5)
        # node 57 is CreateVideo
        self.assertEqual(injected["57"]["inputs"]["fps"], 24)


if __name__ == "__main__":
    unittest.main()

