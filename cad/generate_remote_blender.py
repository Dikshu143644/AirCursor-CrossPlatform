"""AirCursor Procedural 3D CAD & Hardware Concept Generator for Blender 5.1.

Generates parametric, production-fidelity 3D CAD models for the 5 AirCursor physical remote concepts:
  - Concept 1: AirRing Pro (Index finger smart ring, micro optical trackball, capacitive touch bezel, 6-axis IMU)
  - Concept 2: AirWand Elite (Contoured ergonomic air-mouse wand, index trigger, thumb rocker, AirPods stem squeeze pads)
  - Concept 3: AirPebble Touch (Organic river-stone puck, full-surface multi-touch dome, rotary aluminum dial)
  - Concept 4: AirClip Mini (14g eyewear/collar clip, micro toggle switch, capacitive tap pad, high-precision IMU)
  - Concept 5: AirDeck Controller (Compact handheld asymmetric thumb-deck, thumb trackpad, shoulder triggers, OLED status pill)

Usage within Blender 5.1:
  "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" --background --python cad/generate_remote_blender.py -- [options]

Options:
  --concept 1|2|3|4|5|all    Concept ID(s) to generate (default: all)
  --render                   Render high-resolution thumbnail images to cad/renders/
  --export FORMAT            Export format(s): obj, gltf, stl, blend, all (comma-separated, default: all)
  --output_dir PATH          Output directory for models (default: cad/models)
  --render_dir PATH          Output directory for renders (default: cad/renders)
  --samples INT              Render sample count (default: 16 for fast high-quality Cycles)
  --resolution WxH           Render resolution (default: 1920x1080)
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys

# Check if running inside Blender
try:
    import bpy
    import bmesh
    import mathutils
    IS_BLENDER = True
except ImportError:
    IS_BLENDER = False


# ============================================================================
# CONCEPT METADATA DEFINITIONS
# ============================================================================

CONCEPTS_METADATA = {
    1: {
        "id": 1,
        "name": "AirRing_Pro",
        "title": "AirRing Pro",
        "description": "Index finger smart ring with micro optical trackball, capacitive touch bezel, and 6-axis IMU",
        "dimensions_mm": {"outer_diameter": 23.8, "inner_bore": 19.8, "width": 8.4, "thickness": 2.0},
        "mass_grams": 8.8,
        "primary_material": "Grade 5 Titanium (Ti-6Al-4V) with PEEK Bio-Resin Liner",
    },
    2: {
        "id": 2,
        "name": "AirWand_Elite",
        "title": "AirWand Elite",
        "description": "Contoured ergonomic air-mouse wand with index trigger, thumb rocker, and stem squeeze pads",
        "dimensions_mm": {"length": 132.0, "max_width": 28.5, "neck_width": 18.2, "height": 24.0},
        "mass_grams": 52.0,
        "primary_material": "CNC 6061-T6 Aluminum Spine with Fluoroelastomer Lower Grip",
    },
    3: {
        "id": 3,
        "name": "AirPebble_Touch",
        "title": "AirPebble Touch",
        "description": "Organic river-stone puck with full-surface multi-touch dome and rotary aluminum dial",
        "dimensions_mm": {"length": 68.0, "width": 54.0, "height": 19.5, "dial_width": 4.2},
        "mass_grams": 64.0,
        "primary_material": "Corning Gorilla Glass Victus Dome with Knurled 6061 Aluminum Dial and Ceramic Base",
    },
    4: {
        "id": 4,
        "name": "AirClip_Mini",
        "title": "AirClip Mini",
        "description": "14g eyewear and collar lapel clip with micro toggle switch, capacitive tap pad, and precision IMU",
        "dimensions_mm": {"length": 38.5, "width": 14.2, "thickness": 9.8, "jaw_opening": 4.5},
        "mass_grams": 14.0,
        "primary_material": "3K Twill Carbon-Fiber Reinforced Polymer with 301 Stainless Spring Clip",
    },
    5: {
        "id": 5,
        "name": "AirDeck_Controller",
        "title": "AirDeck Controller",
        "description": "Compact handheld asymmetric thumb-deck with thumb trackpad, shoulder triggers, and OLED status pill",
        "dimensions_mm": {"length": 88.0, "width": 46.0, "height": 22.0, "pad_diameter": 22.0},
        "mass_grams": 68.0,
        "primary_material": "Die-Cast AZ91D Magnesium Alloy with Textured PBT and Cobalt Blue Triggers",
    },
}


# ============================================================================
# MATERIAL GENERATION (PBR METALLIC/ROUGHNESS & EMISSIVE)
# ============================================================================

def get_or_create_material(name: str, **kwargs) -> bpy.types.Material:
    """Creates or retrieves a photorealistic PBR material using Blender 5.1 Principled BSDF."""
    if not IS_BLENDER:
        return None

    if name in bpy.data.materials:
        return bpy.data.materials[name]

    mat = bpy.data.materials.new(name=name)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        try:
            mat.use_nodes = True
        except Exception:
            pass
    tree = mat.node_tree
    nodes = tree.nodes
    bsdf = nodes.get("Principled BSDF")

    if bsdf:
        # Helper to set input socket safely across Blender RNA versions
        def set_socket(socket_name: str, value):
            if socket_name in bsdf.inputs:
                bsdf.inputs[socket_name].default_value = value

        # Set Base Color
        if "base_color" in kwargs:
            set_socket("Base Color", kwargs["base_color"])

        # Set Metallic
        if "metallic" in kwargs:
            set_socket("Metallic", kwargs["metallic"])

        # Set Roughness
        if "roughness" in kwargs:
            set_socket("Roughness", kwargs["roughness"])

        # Set Transmission
        if "transmission" in kwargs:
            if "Transmission Weight" in bsdf.inputs:
                set_socket("Transmission Weight", kwargs["transmission"])
            elif "Transmission" in bsdf.inputs:
                set_socket("Transmission", kwargs["transmission"])

        # Set Clearcoat
        if "clearcoat" in kwargs:
            if "Coat Weight" in bsdf.inputs:
                set_socket("Coat Weight", kwargs["clearcoat"])
            elif "Clearcoat" in bsdf.inputs:
                set_socket("Clearcoat", kwargs["clearcoat"])

        # Set Emission Color & Strength
        if "emission_color" in kwargs:
            set_socket("Emission Color", kwargs["emission_color"])
        if "emission_strength" in kwargs:
            set_socket("Emission Strength", kwargs["emission_strength"])

        # Set IOR
        if "ior" in kwargs:
            set_socket("IOR", kwargs["ior"])

    return mat


def build_material_palette() -> dict[str, bpy.types.Material]:
    """Instantiates the complete AirCursor CMF material palette."""
    palette = {}

    # Titanium Satin PVD Space Gray
    palette["Titanium_SpaceGray"] = get_or_create_material(
        "Titanium_SpaceGray",
        base_color=(0.35, 0.36, 0.38, 1.0),
        metallic=0.92,
        roughness=0.28,
        clearcoat=0.2
    )

    # Hypoallergenic PEEK Bio-Resin Liner
    palette["PEEK_BioResin"] = get_or_create_material(
        "PEEK_BioResin",
        base_color=(0.08, 0.08, 0.09, 1.0),
        metallic=0.05,
        roughness=0.62
    )

    # Synthetic Ruby Optical Trackball
    palette["Ruby_Optical"] = get_or_create_material(
        "Ruby_Optical",
        base_color=(0.78, 0.02, 0.08, 1.0),
        metallic=0.1,
        roughness=0.04,
        clearcoat=1.0,
        ior=1.77
    )

    # Signature AirCursor Cyan LED Glow
    palette["AirCursor_Cyan_Glow"] = get_or_create_material(
        "AirCursor_Cyan_Glow",
        base_color=(0.0, 0.9, 1.0, 1.0),
        emission_color=(0.0, 0.9, 1.0, 1.0),
        emission_strength=8.0,
        roughness=0.1
    )

    # Anodized Midnight Black 6061-T6 Aluminum
    palette["Aluminum_Midnight"] = get_or_create_material(
        "Aluminum_Midnight",
        base_color=(0.12, 0.13, 0.15, 1.0),
        metallic=0.88,
        roughness=0.32
    )

    # Soft-Touch Medical Fluoroelastomer (Shore 55A)
    palette["Fluoroelastomer_Matte"] = get_or_create_material(
        "Fluoroelastomer_Matte",
        base_color=(0.15, 0.16, 0.18, 1.0),
        metallic=0.0,
        roughness=0.78
    )

    # Frosted Gorilla Glass Victus Multi-Touch Dome
    palette["GorillaGlass_Frosted"] = get_or_create_material(
        "GorillaGlass_Frosted",
        base_color=(0.88, 0.92, 0.96, 1.0),
        metallic=0.08,
        roughness=0.18,
        transmission=0.82,
        clearcoat=0.6,
        ior=1.52
    )

    # Knurled Natural Silver Aluminum Dial Crown
    palette["Aluminum_Knurled_Silver"] = get_or_create_material(
        "Aluminum_Knurled_Silver",
        base_color=(0.82, 0.84, 0.88, 1.0),
        metallic=0.96,
        roughness=0.20
    )

    # Zirconia Ceramic Satin White Base
    palette["Ceramic_Zirconia"] = get_or_create_material(
        "Ceramic_Zirconia",
        base_color=(0.92, 0.93, 0.95, 1.0),
        metallic=0.12,
        roughness=0.35
    )

    # 3K Twill Carbon-Fiber Reinforced Polymer
    palette["CarbonFiber_3K"] = get_or_create_material(
        "CarbonFiber_3K",
        base_color=(0.14, 0.14, 0.15, 1.0),
        metallic=0.35,
        roughness=0.42,
        clearcoat=0.4
    )

    # 301 Stainless Steel Spring
    palette["StainlessSteel_301"] = get_or_create_material(
        "StainlessSteel_301",
        base_color=(0.65, 0.68, 0.72, 1.0),
        metallic=0.95,
        roughness=0.22
    )

    # Anodized Electric Crimson Toggle Switch
    palette["Anodized_Crimson"] = get_or_create_material(
        "Anodized_Crimson",
        base_color=(0.85, 0.08, 0.12, 1.0),
        metallic=0.75,
        roughness=0.25
    )

    # AZ91D Magnesium Alloy Chassis
    palette["Magnesium_Chassis"] = get_or_create_material(
        "Magnesium_Chassis",
        base_color=(0.85, 0.87, 0.90, 1.0),
        metallic=0.82,
        roughness=0.38
    )

    # Cobalt Blue Metallic Shoulder Triggers
    palette["Cobalt_Blue_Metallic"] = get_or_create_material(
        "Cobalt_Blue_Metallic",
        base_color=(0.06, 0.32, 0.82, 1.0),
        metallic=0.85,
        roughness=0.26
    )

    # Monochrome OLED Status Display Pill
    palette["OLED_Display_Screen"] = get_or_create_material(
        "OLED_Display_Screen",
        base_color=(0.02, 0.02, 0.03, 1.0),
        emission_color=(0.15, 0.28, 0.38, 1.0),
        emission_strength=1.5,
        roughness=0.08
    )

    # Gold-Plated Pogo Charging Contacts
    palette["Gold_Plated_Contacts"] = get_or_create_material(
        "Gold_Plated_Contacts",
        base_color=(1.0, 0.78, 0.18, 1.0),
        metallic=0.98,
        roughness=0.14
    )

    return palette


# ============================================================================
# PROCEDURAL MESH GENERATION FOR THE 5 CONCEPTS
# ============================================================================

def clear_scene():
    """Removes all objects, meshes, materials, and lights from the active scene."""
    if not IS_BLENDER:
        return
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)
    for light in bpy.data.lights:
        bpy.data.lights.remove(light)
    for cam in bpy.data.cameras:
        bpy.data.cameras.remove(cam)


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material):
    """Safely appends a material to an object."""
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


def set_smooth_shading(obj: bpy.types.Object):
    """Enables auto smooth shading on the given mesh object."""
    mesh = obj.data
    for p in mesh.polygons:
        p.use_smooth = True


# ----------------------------------------------------------------------------
# CONCEPT 1: AirRing Pro
# ----------------------------------------------------------------------------
def build_concept_1_airring_pro(palette: dict) -> list[bpy.types.Object]:
    """Procedurally generates Concept 1: AirRing Pro."""
    objects = []

    # 1. Outer Titanium Torus Band (OD 23.8mm, Wall 2.0mm)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.0109,
        minor_radius=0.0016,
        major_segments=64,
        minor_segments=32,
        location=(0, 0, 0)
    )
    outer_band = bpy.context.active_object
    outer_band.name = "AirRing_OuterBand_Titanium"
    assign_material(outer_band, palette["Titanium_SpaceGray"])
    set_smooth_shading(outer_band)
    objects.append(outer_band)

    # 2. Inner PEEK Bio-Resin Liner (ID 19.8mm, Width 8.4mm)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.0099,
        depth=0.0084,
        vertices=48,
        location=(0, 0, 0)
    )
    inner_liner = bpy.context.active_object
    inner_liner.name = "AirRing_InnerLiner_PEEK"
    inner_liner.rotation_euler = (math.pi / 2, 0, 0)
    assign_material(inner_liner, palette["PEEK_BioResin"])
    set_smooth_shading(inner_liner)
    objects.append(inner_liner)

    # 3. Top Sensor Dome / Facet Housing (Flattened 12 o'clock pad)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, 0, 0.0125)
    )
    facet = bpy.context.active_object
    facet.name = "AirRing_TopFacet"
    facet.scale = (0.0065, 0.0080, 0.0022)
    assign_material(facet, palette["Titanium_SpaceGray"])
    # Apply bevel modifier for smooth chamfer
    bev = facet.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = 0.0006
    bev.segments = 3
    objects.append(facet)

    # 4. Micro Optical Trackball (3.2mm Ruby Ball)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.0016,
        segments=32,
        ring_count=24,
        location=(0, 0, 0.0138)
    )
    ball = bpy.context.active_object
    ball.name = "AirRing_OpticalTrackball_Ruby"
    assign_material(ball, palette["Ruby_Optical"])
    set_smooth_shading(ball)
    objects.append(ball)

    # 5. Cyan LED Bezel Accent Ring
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.0024,
        minor_radius=0.00025,
        major_segments=32,
        minor_segments=16,
        location=(0, 0, 0.0136)
    )
    led_ring = bpy.context.active_object
    led_ring.name = "AirRing_LED_Accent"
    assign_material(led_ring, palette["AirCursor_Cyan_Glow"])
    set_smooth_shading(led_ring)
    objects.append(led_ring)

    # 6. Gold-Plated Magnetic Pogo Charging Pins (Bottom 6 o'clock position)
    for pin_x in (-0.0016, 0.0016):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.00045,
            depth=0.0012,
            vertices=16,
            location=(pin_x, 0, -0.0122)
        )
        pogo = bpy.context.active_object
        pogo.name = f"AirRing_PogoPin_{'L' if pin_x < 0 else 'R'}"
        assign_material(pogo, palette["Gold_Plated_Contacts"])
        objects.append(pogo)

    return objects


# ----------------------------------------------------------------------------
# CONCEPT 2: AirWand Elite
# ----------------------------------------------------------------------------
def build_concept_2_airwand_elite(palette: dict) -> list[bpy.types.Object]:
    """Procedurally generates Concept 2: AirWand Elite."""
    objects = []

    # 1. Sculpted Wand Upper Spine (Length 132mm, 18 deg inclination)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.0125,
        depth=0.132,
        vertices=48,
        location=(0, 0, 0)
    )
    wand_body = bpy.context.active_object
    wand_body.name = "AirWand_MainSpine_Aluminum"
    wand_body.rotation_euler = (0, math.radians(-14), 0)
    wand_body.scale = (1.0, 0.85, 1.0)
    assign_material(wand_body, palette["Aluminum_Midnight"])
    set_smooth_shading(wand_body)
    objects.append(wand_body)

    # 2. Soft-Touch Lower Fluoroelastomer Grip Sleeve
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.0135,
        depth=0.068,
        vertices=48,
        location=(0.004, 0, -0.028)
    )
    grip = bpy.context.active_object
    grip.name = "AirWand_LowerGrip_Rubber"
    grip.rotation_euler = (0, math.radians(-14), 0)
    grip.scale = (1.02, 0.90, 1.0)
    assign_material(grip, palette["Fluoroelastomer_Matte"])
    set_smooth_shading(grip)
    objects.append(grip)

    # 3. Ergonomic Index Trigger (Underside Recessed Lever)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(-0.014, 0, 0.018)
    )
    trigger = bpy.context.active_object
    trigger.name = "AirWand_IndexTrigger"
    trigger.scale = (0.005, 0.009, 0.016)
    trigger.rotation_euler = (0, math.radians(22), 0)
    assign_material(trigger, palette["Titanium_SpaceGray"])
    bev = trigger.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = 0.001
    bev.segments = 3
    objects.append(trigger)

    # 4. 5-Way Thumb Navigation Rocker Pill (Top)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0.012, 0, 0.038)
    )
    rocker = bpy.context.active_object
    rocker.name = "AirWand_ThumbRocker_5Way"
    rocker.scale = (0.004, 0.010, 0.022)
    rocker.rotation_euler = (0, math.radians(-14), 0)
    assign_material(rocker, palette["Titanium_SpaceGray"])
    bev2 = rocker.modifiers.new(name="Bevel", type='BEVEL')
    bev2.width = 0.0012
    bev2.segments = 3
    objects.append(rocker)

    # 5. Dual Lateral Stem Squeeze Sensor Pads (Left & Right Flanks)
    for side_sign, side_name in ((-1, "L"), (1, "R")):
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(0.002, side_sign * 0.0118, 0.008)
        )
        squeeze = bpy.context.active_object
        squeeze.name = f"AirWand_SqueezePad_{side_name}"
        squeeze.scale = (0.0025, 0.0015, 0.028)
        squeeze.rotation_euler = (0, math.radians(-14), 0)
        assign_material(squeeze, palette["PEEK_BioResin"])
        objects.append(squeeze)

    # 6. AirCursor Signature Cyan Glow Ring (Front Sensor Tip)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.0118,
        minor_radius=0.0009,
        major_segments=48,
        minor_segments=16,
        location=(0.015, 0, 0.060)
    )
    glow_ring = bpy.context.active_object
    glow_ring.name = "AirWand_CyanEmitterRing"
    glow_ring.rotation_euler = (0, math.radians(-14), 0)
    assign_material(glow_ring, palette["AirCursor_Cyan_Glow"])
    set_smooth_shading(glow_ring)
    objects.append(glow_ring)

    # 7. USB-C & Magnetic Dock Collar (Base)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.0085,
        depth=0.004,
        vertices=32,
        location=(-0.015, 0, -0.064)
    )
    base_dock = bpy.context.active_object
    base_dock.name = "AirWand_DockBase"
    base_dock.rotation_euler = (0, math.radians(-14), 0)
    assign_material(base_dock, palette["Aluminum_Midnight"])
    objects.append(base_dock)

    return objects


# ----------------------------------------------------------------------------
# CONCEPT 3: AirPebble Touch
# ----------------------------------------------------------------------------
def build_concept_3_airpebble_touch(palette: dict) -> list[bpy.types.Object]:
    """Procedurally generates Concept 3: AirPebble Touch."""
    objects = []

    # 1. Zirconia Ceramic Base Chassis (68mm x 54mm x 8mm elliptical puck)
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.027,
        depth=0.008,
        vertices=64,
        location=(0, 0, -0.004)
    )
    base_chassis = bpy.context.active_object
    base_chassis.name = "AirPebble_CeramicBase"
    base_chassis.scale = (1.26, 1.0, 1.0)
    assign_material(base_chassis, palette["Ceramic_Zirconia"])
    set_smooth_shading(base_chassis)
    objects.append(base_chassis)

    # 2. Knurled 6061-T6 Aluminum Rotary Dial Crown Ring (64 Detents)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.0275,
        minor_radius=0.0018,
        major_segments=64,
        minor_segments=24,
        location=(0, 0, 0.001)
    )
    dial_ring = bpy.context.active_object
    dial_ring.name = "AirPebble_RotaryDial_Knurled"
    dial_ring.scale = (1.26, 1.0, 1.0)
    assign_material(dial_ring, palette["Aluminum_Knurled_Silver"])
    set_smooth_shading(dial_ring)
    objects.append(dial_ring)

    # 3. Frosted Gorilla Glass Victus Multi-Touch Dome Top
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.034,
        segments=64,
        ring_count=32,
        location=(0, 0, -0.016)
    )
    glass_dome = bpy.context.active_object
    glass_dome.name = "AirPebble_FrostedGlass_Dome"
    glass_dome.scale = (1.0, 0.80, 0.42)
    assign_material(glass_dome, palette["GorillaGlass_Frosted"])
    set_smooth_shading(glass_dome)
    objects.append(glass_dome)

    # 4. Perimeter Cyan LED Accent Halo
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.0255,
        minor_radius=0.00045,
        major_segments=64,
        minor_segments=16,
        location=(0, 0, 0.0025)
    )
    halo = bpy.context.active_object
    halo.name = "AirPebble_CyanHalo"
    halo.scale = (1.26, 1.0, 1.0)
    assign_material(halo, palette["AirCursor_Cyan_Glow"])
    set_smooth_shading(halo)
    objects.append(halo)

    # 5. Bottom PAW3395 Optical Flow Sensor Aperture & PTFE Skates
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.0035,
        depth=0.0012,
        vertices=24,
        location=(0, 0, -0.0082)
    )
    lens = bpy.context.active_object
    lens.name = "AirPebble_OpticalSensor_Lens"
    assign_material(lens, palette["Ruby_Optical"])
    objects.append(lens)

    return objects


# ----------------------------------------------------------------------------
# CONCEPT 4: AirClip Mini
# ----------------------------------------------------------------------------
def build_concept_4_airclip_mini(palette: dict) -> list[bpy.types.Object]:
    """Procedurally generates Concept 4: AirClip Mini."""
    objects = []

    # 1. 3K Carbon-Fiber Main Enclosure Body (38.5 x 14.2 x 6.5 mm)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, 0, 0.002)
    )
    clip_body = bpy.context.active_object
    clip_body.name = "AirClip_CFRP_MainBody"
    clip_body.scale = (0.0142, 0.0385, 0.0065)
    assign_material(clip_body, palette["CarbonFiber_3K"])
    bev = clip_body.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = 0.0012
    bev.segments = 3
    objects.append(clip_body)

    # 2. 301 Stainless Steel Spring Retention Clip Arm (Underside Jaw)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, -0.002, -0.0045)
    )
    spring_jaw = bpy.context.active_object
    spring_jaw.name = "AirClip_StainlessSpring_Jaw"
    spring_jaw.scale = (0.0118, 0.032, 0.0016)
    spring_jaw.rotation_euler = (math.radians(-6), 0, 0)
    assign_material(spring_jaw, palette["StainlessSteel_301"])
    objects.append(spring_jaw)

    # 3. Capacitive Tap & Swipe Face Zone (Outer Top Face)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, 0.004, 0.0054)
    )
    tap_zone = bpy.context.active_object
    tap_zone.name = "AirClip_CapacitiveTouchPad"
    tap_zone.scale = (0.010, 0.022, 0.0006)
    assign_material(tap_zone, palette["PEEK_BioResin"])
    objects.append(tap_zone)

    # 4. Micro Hardware Mute / Tracking Pause Slide Switch (Crimson Toggle)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0.0075, -0.008, 0.0015)
    )
    slide_sw = bpy.context.active_object
    slide_sw.name = "AirClip_MuteToggle_Crimson"
    slide_sw.scale = (0.002, 0.004, 0.0025)
    assign_material(slide_sw, palette["Anodized_Crimson"])
    objects.append(slide_sw)

    # 5. Micro RGB Pill Status LED
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.00075,
        depth=0.0025,
        vertices=16,
        location=(0, -0.0125, 0.0055)
    )
    status_led = bpy.context.active_object
    status_led.name = "AirClip_StatusLED_Pill"
    status_led.rotation_euler = (0, math.pi / 2, 0)
    assign_material(status_led, palette["AirCursor_Cyan_Glow"])
    objects.append(status_led)

    return objects


# ----------------------------------------------------------------------------
# CONCEPT 5: AirDeck Controller
# ----------------------------------------------------------------------------
def build_concept_5_airdeck_controller(palette: dict) -> list[bpy.types.Object]:
    """Procedurally generates Concept 5: AirDeck Controller."""
    objects = []

    # 1. Magnesium Asymmetric Deck Main Chassis (88 x 46 x 18 mm)
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, 0, 0)
    )
    deck_chassis = bpy.context.active_object
    deck_chassis.name = "AirDeck_Chassis_Magnesium"
    deck_chassis.scale = (0.046, 0.088, 0.018)
    assign_material(deck_chassis, palette["Magnesium_Chassis"])
    bev = deck_chassis.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = 0.0025
    bev.segments = 4
    objects.append(deck_chassis)

    # 2. 22mm Concave Force Thumb Trackpad
    bpy.ops.mesh.primitive_cylinder_add(
        radius=0.011,
        depth=0.0018,
        vertices=48,
        location=(-0.006, 0.014, 0.0094)
    )
    trackpad = bpy.context.active_object
    trackpad.name = "AirDeck_ConcaveTrackpad"
    assign_material(trackpad, palette["PEEK_BioResin"])
    set_smooth_shading(trackpad)
    objects.append(trackpad)

    # 3. Tactile Center Indexing Pip (Cyan Glow)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.0012,
        segments=24,
        ring_count=16,
        location=(-0.006, 0.014, 0.0108)
    )
    pip = bpy.context.active_object
    pip.name = "AirDeck_TrackpadCenterPip"
    assign_material(pip, palette["AirCursor_Cyan_Glow"])
    set_smooth_shading(pip)
    objects.append(pip)

    # 4. 0.49" Curved Monochrome OLED Status Pill
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0.0, -0.024, 0.0092)
    )
    oled = bpy.context.active_object
    oled.name = "AirDeck_OLED_DisplayPill"
    oled.scale = (0.026, 0.012, 0.0012)
    assign_material(oled, palette["OLED_Display_Screen"])
    objects.append(oled)

    # 5. Dual Shoulder Triggers (L1 / R1 Bumpers - Cobalt Blue Anodized)
    for trig_sign, trig_name in ((-1, "L1"), (1, "R1")):
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(trig_sign * 0.0145, 0.044, 0.0035)
        )
        bumper = bpy.context.active_object
        bumper.name = f"AirDeck_ShoulderBumper_{trig_name}"
        bumper.scale = (0.012, 0.006, 0.008)
        assign_material(bumper, palette["Cobalt_Blue_Metallic"])
        bev_t = bumper.modifiers.new(name="Bevel", type='BEVEL')
        bev_t.width = 0.0012
        bev_t.segments = 3
        objects.append(bumper)

    # 6. Tactical Profile Selection Keys (A / B)
    for btn_y, btn_label in ((0.008, "A"), (0.022, "B")):
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.0028,
            depth=0.002,
            vertices=24,
            location=(0.014, btn_y, 0.0096)
        )
        p_btn = bpy.context.active_object
        p_btn.name = f"AirDeck_ProfileBtn_{btn_label}"
        assign_material(p_btn, palette["Titanium_SpaceGray"])
        objects.append(p_btn)

    return objects


def set_linear_interpolation(action):
    """Sets linear keyframe interpolation across both legacy and Blender 5.0+ layered actions."""
    if not action:
        return
    # Legacy actions
    if hasattr(action, "fcurves"):
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
    # Blender 5.0+ layered actions
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in getattr(layer, "strips", []):
                for cb in getattr(strip, "channelbags", []):
                    for fc in getattr(cb, "fcurves", []):
                        for kp in fc.keyframe_points:
                            kp.interpolation = 'LINEAR'


# ============================================================================
# STUDIO LIGHTING & CAMERA RIG WITH 360-DEGREE TURNTABLE ANIMATION
# ============================================================================

def setup_studio_rig(objects: list[bpy.types.Object], add_turntable: bool = True) -> tuple[bpy.types.Object, bpy.types.Object]:
    """Configures 3-point studio lighting, shadow catcher plane, framed camera,
    and turntable orbit keyframes (360-degree rotation over 120 frames at 30fps)."""
    if not IS_BLENDER or not objects:
        return None

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 120
    scene.render.fps = 30

    # Calculate bounding box of all objects
    min_co = [float("inf")] * 3
    max_co = [float("-inf")] * 3

    for obj in objects:
        for corner in obj.bound_box:
            world_co = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                min_co[i] = min(min_co[i], world_co[i])
                max_co[i] = max(max_co[i], world_co[i])

    center = mathutils.Vector(((min_co[0] + max_co[0]) / 2.0,
                              (min_co[1] + max_co[1]) / 2.0,
                              (min_co[2] + max_co[2]) / 2.0))

    diag = math.sqrt(sum((max_co[i] - min_co[i]) ** 2 for i in range(3)))
    diag = max(diag, 0.025)

    # 1. Key Light (Warm Key)
    bpy.ops.object.light_add(
        type='AREA',
        radius=diag * 1.5,
        location=(center.x + diag * 1.8, center.y - diag * 2.2, center.z + diag * 2.5)
    )
    key_light = bpy.context.active_object
    key_light.name = "Studio_KeyLight"
    key_light.data.energy = 180.0 * (diag * 10)
    key_light.data.color = (1.0, 0.95, 0.90)

    # 2. Fill Light (Soft Cool Fill)
    bpy.ops.object.light_add(
        type='AREA',
        radius=diag * 2.0,
        location=(center.x - diag * 2.5, center.y - diag * 1.5, center.z + diag * 1.2)
    )
    fill_light = bpy.context.active_object
    fill_light.name = "Studio_FillLight"
    fill_light.data.energy = 85.0 * (diag * 10)
    fill_light.data.color = (0.85, 0.92, 1.0)

    # 3. Rim / Accent Light (Cyan Backlight)
    bpy.ops.object.light_add(
        type='SPOT',
        radius=diag * 0.8,
        location=(center.x - diag * 1.5, center.y + diag * 2.5, center.z + diag * 2.0)
    )
    rim_light = bpy.context.active_object
    rim_light.name = "Studio_RimLight_Cyan"
    rim_light.data.energy = 140.0 * (diag * 10)
    rim_light.data.color = (0.0, 0.90, 1.0)
    rim_light.data.spot_size = math.radians(65)

    # 4. Shadow Catcher Ground Plane
    bpy.ops.mesh.primitive_plane_add(
        size=diag * 20,
        location=(center.x, center.y, min_co[2] - 0.001)
    )
    ground = bpy.context.active_object
    ground.name = "Studio_ShadowCatcher"
    ground.is_shadow_catcher = True

    # 5. Turntable Pivot Empty (Centered on model)
    pivot = bpy.data.objects.new("Camera_Pivot_Turntable", None)
    pivot.empty_display_type = 'ARROWS'
    pivot.empty_display_size = diag * 0.5
    pivot.location = center
    bpy.context.scene.collection.objects.link(pivot)

    # 6. Camera Framed at 3/4 Perspective Angle
    bpy.ops.object.camera_add(location=(0, 0, 0))
    cam = bpy.context.active_object
    cam.name = "Studio_Camera_Beauty"
    cam.data.lens = 85.0  # 85mm portrait telephoto
    cam.data.clip_start = 0.005
    cam.data.clip_end = 100.0
    bpy.context.scene.camera = cam

    # Position camera back along 3/4 vector
    dist = diag * 3.4
    cam_pos = center + mathutils.Vector((dist * 0.72, -dist * 0.95, dist * 0.65))
    cam.location = cam_pos

    # Point directly at center
    direction = center - cam_pos
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam.rotation_euler = rot_quat.to_euler()

    # Parent camera to pivot maintaining world orientation
    cam.parent = pivot
    cam.matrix_parent_inverse = pivot.matrix_world.inverted()

    # 7. Add Turntable 360-Degree Orbit Animation Keyframes (120 frames @ 30fps)
    if add_turntable:
        # Frame 1: 0 degrees
        pivot.rotation_euler = (0, 0, 0)
        pivot.keyframe_insert(data_path="rotation_euler", frame=1)

        # Frame 120: 357 degrees (linear progression)
        pivot.rotation_euler = (0, 0, 2 * math.pi * (119.0 / 120.0))
        pivot.keyframe_insert(data_path="rotation_euler", frame=120)

        # Frame 121: 360 degrees (seamless loop return point)
        pivot.rotation_euler = (0, 0, 2 * math.pi)
        pivot.keyframe_insert(data_path="rotation_euler", frame=121)

        # Linear interpolation for continuous smooth 360-degree orbit
        if pivot.animation_data and pivot.animation_data.action:
            try:
                set_linear_interpolation(pivot.animation_data.action)
            except Exception:
                pass

    return cam


# ============================================================================
# EXPORT OPERATOR WRAPPERS
# ============================================================================

def export_concept(concept_id: int, objects: list[bpy.types.Object], formats: list[str], output_dir: Path):
    """Exports the generated 3D concept to selected formats (.obj, .gltf/.glb, .stl, .blend)."""
    if not IS_BLENDER:
        return

    meta = CONCEPTS_METADATA[concept_id]
    base_name = f"concept_{concept_id}_{meta['name'].lower()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Select only the concept objects
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]

    for fmt in formats:
        fmt_clean = fmt.strip().lower()
        if fmt_clean in ("obj", ".obj"):
            out_file = output_dir / f"{base_name}.obj"
            try:
                bpy.ops.wm.obj_export(filepath=str(out_file), export_selected_objects=True)
                print(f"[EXPORT] OBJ written: {out_file} ({out_file.stat().st_size} bytes)")
            except Exception as e:
                print(f"[WARN] OBJ export error: {e}")

        elif fmt_clean in ("gltf", "glb", ".gltf", ".glb"):
            out_file = output_dir / f"{base_name}.glb"
            try:
                bpy.ops.export_scene.gltf(filepath=str(out_file), use_selection=True)
                print(f"[EXPORT] GLTF written: {out_file} ({out_file.stat().st_size} bytes)")
            except Exception as e:
                print(f"[WARN] GLTF export error: {e}")

        elif fmt_clean in ("stl", ".stl"):
            out_file = output_dir / f"{base_name}.stl"
            try:
                bpy.ops.wm.stl_export(filepath=str(out_file), export_selected_objects=True)
                print(f"[EXPORT] STL written: {out_file} ({out_file.stat().st_size} bytes)")
            except Exception as e:
                print(f"[WARN] STL export error: {e}")

        elif fmt_clean in ("blend", ".blend"):
            out_file = output_dir / f"{base_name}.blend"
            try:
                bpy.ops.wm.save_as_mainfile(
                    filepath=str(out_file.resolve()),
                    copy=True,
                    check_existing=False
                )
                print(f"[EXPORT] BLEND written: {out_file} ({out_file.stat().st_size} bytes)")
            except Exception as e:
                print(f"[WARN] BLEND export error: {e}")


# ============================================================================
# UNIFIED ALL-5 PRODUCTS SHOWCASE SCENE & EXPORT
# ============================================================================

def build_all_5_products_showcase(output_dir: Path, export_formats: list[str] | None = None) -> list[bpy.types.Object]:
    """Builds a unified 5-concept product showcase scene on a presentation pedestal
    with 3D embossed nameplates, 3-point studio lighting, and 360-degree turntable
    camera animation keyframes (120 frames at 30fps). Saves 'all_5_products_showcase.blend'."""
    if not IS_BLENDER:
        return []

    print("\n>>> Generating Unified All-5 Products Showcase Scene...")
    clear_scene()
    palette = build_material_palette()
    output_dir.mkdir(parents=True, exist_ok=True)

    spacing = 0.16
    offsets = {
        1: -2 * spacing, # -0.32m (AirRing Pro)
        2: -1 * spacing, # -0.16m (AirWand Elite)
        3: 0.0,          #  0.00m (AirPebble Touch)
        4: 1 * spacing,  # +0.16m (AirClip Mini)
        5: 2 * spacing,  # +0.32m (AirDeck Controller)
    }

    builders = {
        1: (build_concept_1_airring_pro, "01_AirRing_Pro", "AIRRING PRO"),
        2: (build_concept_2_airwand_elite, "02_AirWand_Elite", "AIRWAND ELITE"),
        3: (build_concept_3_airpebble_touch, "03_AirPebble_Touch", "AIRPEBBLE TOUCH"),
        4: (build_concept_4_airclip_mini, "04_AirClip_Mini", "AIRCLIP MINI"),
        5: (build_concept_5_airdeck_controller, "05_AirDeck_Controller", "AIRDECK CONTROLLER"),
    }

    showcase_col = bpy.data.collections.new("AirCursor_Remote_Concepts")
    bpy.context.scene.collection.children.link(showcase_col)

    all_showcase_objs = []

    for cid, (builder_fn, col_name, title) in builders.items():
        sub_col = bpy.data.collections.new(col_name)
        showcase_col.children.link(sub_col)

        objs = builder_fn(palette)
        min_z = float("inf")
        for o in objs:
            for corner in o.bound_box:
                w_co = o.matrix_world @ mathutils.Vector(corner)
                min_z = min(min_z, w_co.z)

        z_shift = -min_z if min_z != float("inf") else 0.0
        x_shift = offsets[cid]

        for o in objs:
            if o.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(o)
            if o.name not in sub_col.objects:
                sub_col.objects.link(o)
            o.location.x += x_shift
            o.location.z += z_shift
            all_showcase_objs.append(o)

    # Presentation Pedestal Plinth
    bpy.ops.mesh.primitive_cube_add(
        size=1.0,
        location=(0, 0, -0.01)
    )
    pedestal = bpy.context.active_object
    pedestal.name = "Showcase_Pedestal"
    pedestal.scale = (0.85, 0.28, 0.02)
    p_mat = get_or_create_material(
        "Pedestal_Material",
        base_color=(0.04, 0.05, 0.07, 1.0),
        metallic=0.8,
        roughness=0.35
    )
    assign_material(pedestal, p_mat)
    bev = pedestal.modifiers.new(name="Bevel", type='BEVEL')
    bev.width = 0.003
    bev.segments = 3
    all_showcase_objs.append(pedestal)

    # 3D Embossed Metallic Text Labels
    metal_mat = palette.get("Titanium_SpaceGray")
    for cid, (_, _, title) in builders.items():
        x_pos = offsets[cid]
        font_curve = bpy.data.curves.new(type="FONT", name=f"Label_{cid}_Curve")
        font_curve.body = title
        font_curve.size = 0.010
        font_curve.extrude = 0.0012
        font_curve.bevel_depth = 0.0003
        txt_obj = bpy.data.objects.new(f"Label_{cid}_{title.replace(' ', '_')}", font_curve)
        bpy.context.scene.collection.objects.link(txt_obj)
        txt_obj.location = (x_pos - 0.04, -0.09, 0.001)
        txt_obj.rotation_euler = (math.radians(70), 0, 0)
        if metal_mat:
            txt_obj.data.materials.append(metal_mat)
        all_showcase_objs.append(txt_obj)

    # Configure studio lighting, camera, and turntable 360-deg animation (120 frames @ 30fps)
    setup_studio_rig(all_showcase_objs, add_turntable=True)

    # Save all_5_products_showcase.blend
    blend_file = output_dir / "all_5_products_showcase.blend"
    try:
        bpy.ops.wm.save_as_mainfile(
            filepath=str(blend_file.resolve()),
            copy=True,
            check_existing=False
        )
        print(f"[SHOWCASE] Unified blend written: {blend_file} ({blend_file.stat().st_size} bytes)")
    except Exception as e:
        print(f"[WARN] Showcase blend save error: {e}")

    # Export formats if specified
    if export_formats:
        bpy.ops.object.select_all(action='SELECT')
        for fmt in export_formats:
            fmt_clean = fmt.strip().lower()
            if fmt_clean in ("glb", "gltf", ".glb", ".gltf"):
                glb_file = output_dir / "all_5_products_showcase.glb"
                try:
                    bpy.ops.export_scene.gltf(filepath=str(glb_file.resolve()), use_selection=True)
                    print(f"[SHOWCASE] Unified GLB written: {glb_file} ({glb_file.stat().st_size} bytes)")
                except Exception as e:
                    print(f"[WARN] Showcase GLTF export error: {e}")
            elif fmt_clean in ("obj", ".obj"):
                obj_file = output_dir / "all_5_products_showcase.obj"
                try:
                    bpy.ops.wm.obj_export(filepath=str(obj_file.resolve()), export_selected_objects=True)
                    print(f"[SHOWCASE] Unified OBJ written: {obj_file} ({obj_file.stat().st_size} bytes)")
                except Exception as e:
                    print(f"[WARN] Showcase OBJ export error: {e}")
            elif fmt_clean in ("stl", ".stl"):
                stl_file = output_dir / "all_5_products_showcase.stl"
                try:
                    bpy.ops.wm.stl_export(filepath=str(stl_file.resolve()), export_selected_objects=True)
                    print(f"[SHOWCASE] Unified STL written: {stl_file} ({stl_file.stat().st_size} bytes)")
                except Exception as e:
                    print(f"[WARN] Showcase STL export error: {e}")

    return all_showcase_objs


# ============================================================================
# RENDERING PIPELINE
# ============================================================================

def render_thumbnail(concept_id: int, render_dir: Path, resolution: tuple[int, int], samples: int):
    """Renders high-resolution thumbnail using Blender Cycles / Workbench."""
    if not IS_BLENDER:
        return

    meta = CONCEPTS_METADATA[concept_id]
    base_name = f"concept_{concept_id}_{meta['name'].lower()}"
    render_dir.mkdir(parents=True, exist_ok=True)
    out_img = render_dir / f"{base_name}.png"

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.filepath = str(out_img.resolve())

    print(f"[RENDER] Rendering {base_name} ({resolution[0]}x{resolution[1]} @ {samples} samples)...")
    try:
        bpy.ops.render.render(write_still=True)
        if out_img.exists():
            print(f"[RENDER] Thumbnail written: {out_img} ({out_img.stat().st_size} bytes)")
    except Exception as e:
        print(f"[ERROR] Render failed: {e}")


# ============================================================================
# CLI ARGUMENT PARSER & ORCHESTRATION
# ============================================================================

def parse_cli_args(args_list: list[str]) -> argparse.Namespace:
    """Parses command-line arguments passed after '--' in Blender invocation."""
    parser = argparse.ArgumentParser(
        description="AirCursor Blender 5.1 Procedural CAD & Remote Concept Generator"
    )
    parser.add_argument(
        "--concept", "-c",
        type=str,
        default="all",
        help="Concept ID to generate (1, 2, 3, 4, 5, or 'all')"
    )
    parser.add_argument(
        "--render", "-r",
        action="store_true",
        help="Render high-res PNG thumbnail image"
    )
    parser.add_argument(
        "--export", "-e",
        type=str,
        default="all",
        help="Export formats: obj, gltf, stl, blend, all (comma-separated)"
    )
    parser.add_argument(
        "--output_dir", "-o",
        type=str,
        default=str(Path(__file__).resolve().parent / "models"),
        help="Output directory for exported 3D CAD models"
    )
    parser.add_argument(
        "--render_dir",
        type=str,
        default=str(Path(__file__).resolve().parent / "renders"),
        help="Output directory for rendered PNG images"
    )
    parser.add_argument(
        "--showcase", "-s",
        action="store_true",
        help="Generate unified all-5 products showcase scene with turntable animation"
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=16,
        help="Cycles render sample count (default: 16)"
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default="1280x720",
        help="Render resolution WxH (default: 1280x720)"
    )

    return parser.parse_args(args_list)


def run_generator(cli_args: list[str] | None = None):
    """Main execution entry point."""
    if cli_args is None:
        # Extract arguments passed after '--' in Blender command line
        if "--" in sys.argv:
            idx = sys.argv.index("--")
            cli_args = sys.argv[idx + 1:]
        else:
            cli_args = []

    # If first argument is just a bare concept number (e.g. '1'), support it conveniently
    if cli_args and cli_args[0] in ("1", "2", "3", "4", "5", "all") and not cli_args[0].startswith("-"):
        cli_args = ["--concept", cli_args[0]] + cli_args[1:]

    args = parse_cli_args(cli_args)

    # Determine concept IDs to generate
    if args.concept.strip().lower() == "all":
        target_ids = [1, 2, 3, 4, 5]
    else:
        target_ids = [int(args.concept.strip())]

    # Parse export formats
    if args.export.strip().lower() == "all":
        export_formats = ["blend", "gltf", "obj", "stl"]
    else:
        export_formats = [f.strip().lower() for f in args.export.split(",") if f.strip()]

    # Parse resolution
    try:
        w_str, h_str = args.resolution.lower().split("x")
        res_tuple = (int(w_str), int(h_str))
    except Exception:
        res_tuple = (1280, 720)

    output_dir = Path(args.output_dir).resolve()
    render_dir = Path(args.render_dir).resolve()

    print("=" * 72)
    print(" AirCursor 3D CAD & Procedural Remote Concept Generator (Blender 5.1)")
    print(f" Targets: {target_ids}")
    print(f" Export Formats: {export_formats}")
    print(f" Render Enabled: {args.render} (Resolution: {res_tuple[0]}x{res_tuple[1]}, Samples: {args.samples})")
    print(f" Models Dir: {output_dir}")
    print(f" Renders Dir: {render_dir}")
    print("=" * 72)

    builders = {
        1: build_concept_1_airring_pro,
        2: build_concept_2_airwand_elite,
        3: build_concept_3_airpebble_touch,
        4: build_concept_4_airclip_mini,
        5: build_concept_5_airdeck_controller,
    }

    # If only --showcase is requested without specific concepts
    if args.showcase and args.concept.strip().lower() not in ("all", "1", "2", "3", "4", "5"):
        build_all_5_products_showcase(output_dir, export_formats)
        print("\n[SUCCESS] Unified showcase generation complete.")
        return

    for cid in target_ids:
        print(f"\n>>> Generating Concept {cid}: {CONCEPTS_METADATA[cid]['title']}...")
        clear_scene()
        palette = build_material_palette()

        # Build procedural mesh parts
        objects = builders[cid](palette)
        print(f"    Built {len(objects)} procedural mesh components.")

        # Setup lighting, camera & turntable animation (120 frames @ 30fps)
        setup_studio_rig(objects, add_turntable=True)

        # Export models
        if export_formats:
            export_concept(cid, objects, export_formats, output_dir)

        # Render preview thumbnail
        if args.render:
            render_thumbnail(cid, render_dir, res_tuple, args.samples)

    # If 'all' or '--showcase' was requested, generate the unified showcase scene
    if args.concept.strip().lower() == "all" or args.showcase:
        build_all_5_products_showcase(output_dir, export_formats)

    print("\n[SUCCESS] Procedural CAD generation complete for all requested concepts.")


if __name__ == "__main__" and IS_BLENDER:
    run_generator()
