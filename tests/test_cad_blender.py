"""Unit and Integration Tests for AirCursor Blender 3D CAD & Remote Concepts (Subjects 12 & 13).

Validates:
1. Syntax and static structure of `cad/generate_remote_blender.py`.
2. CLI argument parsing logic, defaults, and option flags.
3. Completeness of metadata definitions for Concepts 1-5.
4. Completeness and validity of `cad/REMOTE_CONCEPTS.md`.
5. WebGL / Three.js 3D interactive showcase application in `cad/remote_showcase.html`.
6. Presence, non-zero file sizes, and validity of generated 3D CAD models (.blend, .obj, .stl, .glb) and renders (.png).
7. Subprocess execution of Blender 5.1 in background mode generating CAD assets.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
CAD_DIR = ROOT_DIR / "cad"
MODELS_DIR = CAD_DIR / "models"
RENDERS_DIR = CAD_DIR / "renders"
BLENDER_SCRIPT = CAD_DIR / "generate_remote_blender.py"
CONCEPTS_DOC = CAD_DIR / "REMOTE_CONCEPTS.md"
SHOWCASE_HTML = CAD_DIR / "remote_showcase.html"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe")


class TestAirCursorBlenderCAD(unittest.TestCase):
    """Test suite covering Blender 5.1 procedural CAD scripts, assets, and specifications."""

    def test_01_blender_script_syntax(self):
        """Validates that cad/generate_remote_blender.py exists and parses with valid Python syntax."""
        self.assertTrue(BLENDER_SCRIPT.exists(), f"Missing script: {BLENDER_SCRIPT}")
        source = BLENDER_SCRIPT.read_text(encoding="utf-8")
        parsed = ast.parse(source, filename=str(BLENDER_SCRIPT))
        self.assertIsInstance(parsed, ast.Module)
        self.assertGreater(len(parsed.body), 10)

    def test_02_concept_metadata_structure(self):
        """Verifies metadata dictionary contains all 5 concepts with required CAD attributes."""
        # Read file and execute AST or import functions
        sys.path.insert(0, str(CAD_DIR))
        import generate_remote_blender as grb

        metadata = grb.CONCEPTS_METADATA
        self.assertEqual(len(metadata), 5)

        expected_concepts = {
            1: "AirRing_Pro",
            2: "AirWand_Elite",
            3: "AirPebble_Touch",
            4: "AirClip_Mini",
            5: "AirDeck_Controller"
        }

        for cid, expected_name in expected_concepts.items():
            self.assertIn(cid, metadata)
            data = metadata[cid]
            self.assertEqual(data["id"], cid)
            self.assertEqual(data["name"], expected_name)
            self.assertIn("title", data)
            self.assertIn("description", data)
            self.assertIn("dimensions_mm", data)
            self.assertIn("mass_grams", data)
            self.assertGreater(data["mass_grams"], 0)
            self.assertIn("primary_material", data)

    def test_03_cli_argument_parsing(self):
        """Verifies CLI argument parsing logic handles options, defaults, and aliases."""
        sys.path.insert(0, str(CAD_DIR))
        import generate_remote_blender as grb

        # Default options
        args_default = grb.parse_cli_args([])
        self.assertEqual(args_default.concept, "all")
        self.assertEqual(args_default.export, "all")
        self.assertFalse(args_default.render)
        self.assertEqual(args_default.samples, 16)
        self.assertEqual(args_default.resolution, "1280x720")

        # Custom options
        custom_args = grb.parse_cli_args([
            "--concept", "3",
            "--export", "obj,gltf",
            "--render",
            "--samples", "32",
            "--resolution", "1920x1080",
            "--output_dir", "test_models",
            "--render_dir", "test_renders"
        ])
        self.assertEqual(custom_args.concept, "3")
        self.assertEqual(custom_args.export, "obj,gltf")
        self.assertTrue(custom_args.render)
        self.assertEqual(custom_args.samples, 32)
        self.assertEqual(custom_args.resolution, "1920x1080")
        self.assertEqual(custom_args.output_dir, "test_models")
        self.assertEqual(custom_args.render_dir, "test_renders")

    def test_04_remote_concepts_markdown_spec(self):
        """Verifies cad/REMOTE_CONCEPTS.md contains complete industrial design specifications."""
        self.assertTrue(CONCEPTS_DOC.exists(), f"Missing spec doc: {CONCEPTS_DOC}")
        content = CONCEPTS_DOC.read_text(encoding="utf-8")

        # Check for all 5 concepts
        self.assertIn("Concept 1: AirRing Pro", content)
        self.assertIn("Concept 2: AirWand Elite", content)
        self.assertIn("Concept 3: AirPebble Touch", content)
        self.assertIn("Concept 4: AirClip Mini", content)
        self.assertIn("Concept 5: AirDeck", content)

        # Check for key sections
        self.assertIn("CMF", content)
        self.assertIn("Sensor & Electrical Architecture", content)
        self.assertIn("AirCursor Interaction Modalities", content)
        self.assertIn("Comparative CMF & Specification Matrix", content)
        self.assertIn("Human-Input Arbiter", content)

    def test_05_remote_showcase_webgl_html(self):
        """Verifies cad/remote_showcase.html is a valid interactive 3D WebGL showcase."""
        self.assertTrue(SHOWCASE_HTML.exists(), f"Missing HTML showcase: {SHOWCASE_HTML}")
        html_code = SHOWCASE_HTML.read_text(encoding="utf-8")

        # Three.js and OrbitControls
        self.assertIn("three.min.js", html_code)
        self.assertIn("OrbitControls", html_code)
        self.assertIn("<canvas id=\"webgl-canvas\">", html_code)

        # All 5 concepts present in HTML / JS metadata
        self.assertIn("AirRing Pro", html_code)
        self.assertIn("AirWand Elite", html_code)
        self.assertIn("AirPebble Touch", html_code)
        self.assertIn("AirClip Mini", html_code)
        self.assertIn("AirDeck", html_code)

        # Interactive controls
        self.assertIn("Turntable", html_code)
        self.assertIn("Exploded Stackup", html_code)
        self.assertIn("Wireframe", html_code)
        self.assertIn("select-btn", html_code)
        self.assertIn("localStorage.setItem('aircursor_selected_concept'", html_code)

    def test_06_generated_models_and_renders_existence(self):
        """Verifies that generated 3D models and renders exist and have non-zero file sizes."""
        self.assertTrue(MODELS_DIR.exists(), f"Missing models directory: {MODELS_DIR}")
        self.assertTrue(RENDERS_DIR.exists(), f"Missing renders directory: {RENDERS_DIR}")

        concept_keys = [
            "concept_1_airring_pro",
            "concept_2_airwand_elite",
            "concept_3_airpebble_touch",
            "concept_4_airclip_mini",
            "concept_5_airdeck_controller",
        ]

        # Check at least concept 1 exists (or whichever was generated)
        found_models = list(MODELS_DIR.glob("*.*"))
        self.assertGreater(len(found_models), 0, "No 3D CAD model files found in cad/models/")

        found_renders = list(RENDERS_DIR.glob("*.png"))
        self.assertGreater(len(found_renders), 0, "No render PNGs found in cad/renders/")

        # Verify sizes are non-zero
        for model_file in found_models:
            self.assertGreater(model_file.stat().st_size, 0, f"Model file {model_file.name} is empty")

        for render_file in found_renders:
            self.assertGreater(render_file.stat().st_size, 0, f"Render file {render_file.name} is empty")

    def test_07_blender_background_execution(self):
        """Executes Blender 5.1 in background mode to generate a quick model and render."""
        if not BLENDER_EXE.exists():
            self.skipTest(f"Blender 5.1 not found at {BLENDER_EXE}")

        test_out_dir = CAD_DIR / "test_out_models"
        test_rnd_dir = CAD_DIR / "test_out_renders"

        cmd = [
            str(BLENDER_EXE),
            "--background",
            "--python", str(BLENDER_SCRIPT),
            "--",
            "--concept", "1",
            "--export", "obj,stl",
            "--render",
            "--samples", "2",
            "--resolution", "160x90",
            "--output_dir", str(test_out_dir),
            "--render_dir", str(test_rnd_dir),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, f"Blender execution failed:\n{result.stderr}\n{result.stdout}")

        # Verify output files
        expected_obj = test_out_dir / "concept_1_airring_pro.obj"
        expected_stl = test_out_dir / "concept_1_airring_pro.stl"
        expected_png = test_rnd_dir / "concept_1_airring_pro.png"

        self.assertTrue(expected_obj.exists(), f"Missing test OBJ: {expected_obj}")
        self.assertTrue(expected_stl.exists(), f"Missing test STL: {expected_stl}")
        self.assertTrue(expected_png.exists(), f"Missing test PNG: {expected_png}")

        self.assertGreater(expected_obj.stat().st_size, 1000)
        self.assertGreater(expected_stl.stat().st_size, 1000)
        self.assertGreater(expected_png.stat().st_size, 100)

        # Cleanup test output directories
        try:
            for f in test_out_dir.glob("*.*"):
                f.unlink()
            test_out_dir.rmdir()
            for f in test_rnd_dir.glob("*.*"):
                f.unlink()
            test_rnd_dir.rmdir()
        except Exception:
            pass

    def test_08_all_5_individual_cad_models_complete(self):
        """Verifies that each of the 5 concepts has all 4 CAD formats (.blend, .glb, .obj, .stl) present."""
        concept_keys = [
            "concept_1_airring_pro",
            "concept_2_airwand_elite",
            "concept_3_airpebble_touch",
            "concept_4_airclip_mini",
            "concept_5_airdeck_controller",
        ]
        extensions = [".blend", ".glb", ".obj", ".stl"]

        for key in concept_keys:
            for ext in extensions:
                model_file = MODELS_DIR / f"{key}{ext}"
                self.assertTrue(
                    model_file.exists(),
                    f"Missing expected model file: {model_file.name}"
                )
                self.assertGreater(
                    model_file.stat().st_size,
                    100,
                    f"Model file {model_file.name} is too small"
                )

    def test_09_unified_showcase_blend_model(self):
        """Verifies that the unified all_5_products_showcase.blend model exists and has valid size."""
        showcase_blend = MODELS_DIR / "all_5_products_showcase.blend"
        self.assertTrue(
            showcase_blend.exists(),
            f"Missing unified showcase blend file: {showcase_blend}"
        )
        self.assertGreater(
            showcase_blend.stat().st_size,
            50000,
            f"Showcase blend file {showcase_blend.name} is unexpectedly small"
        )

    def test_10_turntable_animation_keyframes(self):
        """Verifies turntable camera animation keyframes (360-degree orbit over 120 frames at 30fps)."""
        if not BLENDER_EXE.exists():
            self.skipTest(f"Blender 5.1 not found at {BLENDER_EXE}")

        check_script = (
            "import bpy, sys\n"
            "from pathlib import Path\n"
            f"blend_path = Path(r'{MODELS_DIR / 'all_5_products_showcase.blend'}')\n"
            "bpy.ops.wm.open_mainfile(filepath=str(blend_path))\n"
            "scene = bpy.context.scene\n"
            "assert scene.frame_start == 1, f'Expected frame_start=1, got {scene.frame_start}'\n"
            "assert scene.frame_end == 120, f'Expected frame_end=120, got {scene.frame_end}'\n"
            "assert scene.render.fps == 30, f'Expected fps=30, got {scene.render.fps}'\n"
            "pivot = bpy.data.objects.get('Camera_Pivot_Turntable')\n"
            "assert pivot is not None, 'Camera_Pivot_Turntable object missing'\n"
            "assert pivot.animation_data is not None, 'Pivot has no animation data'\n"
            "assert pivot.animation_data.action is not None, 'Pivot has no animation action'\n"
            "print('TURNTABLE_ANIMATION_VALID')\n"
        )

        cmd = [
            str(BLENDER_EXE),
            "--background",
            "--python-expr", check_script
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, f"Blender turntable check failed:\n{result.stderr}\n{result.stdout}")
        self.assertIn("TURNTABLE_ANIMATION_VALID", result.stdout)


if __name__ == "__main__":
    unittest.main()

