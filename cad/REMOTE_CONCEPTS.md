# DOSCursor Physical Hardware Remote Concepts: Industrial Design & Engineering Specifications
### Engineered by DOS Company | Hardware Engineering & Industrial Design Group

**Document Version:** 2.0.0-DOS  
**Classification:** Enterprise Hardware Architecture — DOS Company  
**Author:** DOS 3D Hardware CAD & Industrial Design Lead  
**Scope:** Concepts 1–5 Parametric Specifications, CMF, Ergonomics, Sensor Architecture, and Blender CAD Integration  

---

## 1. Executive Summary & Design Philosophy

**DOSCursor**, engineered by **DOS Company**, transforms spatial computing by turning subtle head movements and micro-gestures into high-precision pointer navigation. While computer-vision tracking excels at broad, intuitive spatial control, physical interaction thrives when paired with low-latency tactile feedback, tactile indexing, and strain-free micro-actuation.

The **DOSCursor Physical Remote Concepts** (DOSRing Pro, DOSWand Elite, DOSPebble Touch, DOSClip Mini, and DOSDeck Controller) bridge spatial tracking with physical micro-controls. Rather than replacing the spatial pointer, these five hardware archetypes act as symbiotic companions:
1. **Zero-Fatigue Co-Navigation:** Head pose and vision hand tracking drive coarse cursor trajectory across multi-monitor canvases, while thumb and index fingers execute sub-pixel positioning, drag-locking, and velocity scrubbing.
2. **Tactile Grounding:** Physical switches and localized piezoelectric haptics eliminate the uncertainty of dwell clicks and mid-air pinch gestures.
3. **Multi-Modal Redundancy:** Provides immediate fallback when webcams are occluded, in low-light environments, or during high-stakes presentations and CAD drafting sessions.

---

## 2. Comprehensive Industrial Design Specifications

```
+----------------------------------------------------------------------------------------------------+
|                                    DOSCURSOR REMOTE FAMILY (DOS COMPANY)                           |
+-------------------+--------------------+--------------------+--------------------+-----------------+
|  DOSRing Pro      |  DOSWand Elite     |  DOSPebble Touch   |  DOSClip Mini      |  DOSDeck        |
|  (Wearable Ring)  |  (Ergonomic Wand)  |  (Desk River Puck) |  (14g Lapel Clip)  |  (Thumb Deck)   |
|  8.8g | Titanium  |  52g | Aluminum    |  64g | Glass/Alum  |  14g | CFRP/Steel  |  68g | Mg-Alloy |
+-------------------+--------------------+--------------------+--------------------+-----------------+
```

---

### Concept 1: AirRing Pro (Index-Finger Smart Ring)

```
       [ Micro Optical Trackball (3.2mm) ]
                  \     /
              +-------------+
             /   [Cap Bezel] \
            |    .---------.  |  <-- Outer Facet (Grade 5 Titanium)
            |   /           \ |
            |  |  Finger H-  ||  <-- Inner PEEK Bio-Resin Liner (Ø 19.8mm)
            |   \   Bore    / |
            |    '---------'  |
             \   [Pogo Pins] /
              +-------------+
```

#### 1. Ergonomic Persona & Form Factor
- **Wear Position:** Proximal phalanx of the dominant index finger.
- **Form Geometry:** Toroidal band with an asymmetric flattened outer facet at the 12 o'clock position (thumb landing pad). The inner profile features an elliptical ergonomic relief chamfer (1.2mm radius) that prevents vascular constriction during knuckle flexion.
- **Mass & Balance:** **8.8 grams** total weight. Neutral center of gravity centered directly above the finger axis.

#### 2. Dimensions & Mechanical Tolerances
- **Outer Diameter:** 23.8 mm (Size 10 reference standard).
- **Inner Bore Diameter:** 19.8 mm (Accommodates interchangeable modular PEEK elastomer comfort liners from 17.5 mm to 22.2 mm / US Sizes 7–13).
- **Band Width:** 8.4 mm.
- **Wall Thickness:** 2.0 mm (tapering to 3.6 mm at the top sensor dome).
- **Manufacturing Tolerance:** ISO 2768-m (CNC machined surfaces ±0.05 mm, sensor lens seating ±0.02 mm).

#### 3. Color, Material & Finish (CMF)
- **Outer Shell:** Grade 5 Titanium (Ti-6Al-4V), physical vapor deposition (PVD) satin Space Gray (L* 32, a* 0.2, b* -1.1), ceramic bead blasted (Ra 0.4 µm) with diamond-turned high-gloss perimeter chamfers.
- **Inner Core:** Hypoallergenic medical-grade PEEK (Polyetheretherketone) with micro-textured skin-contact grip ridges.
- **Optical Ball:** Polished synthetic ruby / black silicon nitride ball (Ø 3.2 mm, Ra < 0.01 µm).
- **Bezel Ring:** Annular capacitive electrode ring coated with diamond-like carbon (DLC).
- **Ingress Rating:** IP68 (waterproof to 50 meters, sweat and solvent resistant).

#### 4. Sensor & Electrical Architecture
- **Micro Optical Trackball:** PixArt PAT9125 ultra-low power optical motion sensor coupled to an encapsulated 3.2mm ball; resolves up to 1,200 CPI at 120 Hz report rate.
- **Capacitive Touch Bezel:** Azoteq IQS7211A 360° circular trackpad controller for continuous perimeter rotational scrolling.
- **Spatial IMU:** TDK InvenSense ICM-42688-P 6-axis low-noise IMU (200 Hz internal DMP sampling, ±16g, ±2000 dps).
- **Haptic Engine:** TDK PowerHap 2.5G ultra-thin piezoelectric actuator with 120 V step-up driver (delivers 0.5 ms crisp tactile clicks).
- **Processor & Wireless:** Nordic Semiconductor nRF5340 dual-core ARM Cortex-M33 (BLE 5.3, 2.4 GHz proprietary low-latency mode).
- **Battery & Power Budget:** Curved 24 mAh solid-state lithium-ceramic pouch cell; 38 hours continuous tracking, 14 days low-power sleep; 2-pin gold-plated magnetic pogo pads (charge time: 22 minutes to 80%).

#### 5. AirCursor Interaction Modalities
- **Micro-Nudge:** Thumb rolls the optical ball to micro-adjust cursor location by single screen pixels (ideal for UI alignment and CAD drafting).
- **Ring Scroll:** Orbiting the thumb around the capacitive bezel triggers infinite vertical or horizontal scrolling with inertia.
- **Trackball Tap:** Depressing the spring-loaded ball triggers primary left-click; double tap triggers secondary right-click.
- **Spatial Flick:** Holding the capacitive bezel while flicking the hand left/right switches virtual desktops in AirCursor.

---

### Concept 2: AirWand Elite (Contoured Ergonomic Air-Mouse Wand)

```
        [ Optical IR Dome ]
               |
         .-----'-----.
        /   [Rocker]  \   <-- Top Thumb Rocker / D-Pad Pill
       |   [Cyan Ring] |  <-- AirCursor Glow Emitter Accent
       |  (Squeeze L)  |  <-- Left Lateral Stem Squeeze Force Pad
       |               |
       |  [Trigger]    |  <-- Bottom Index Finger Trigger (Recessed)
       |  (Squeeze R)  |  <-- Right Lateral Stem Squeeze Force Pad
        \             /
         |           |    <-- Tapered Ergonomic Shaft (18° Wrist Inclination)
         |  AirCursor|
         '-----------'
         [ USB-C / Dock ]
```

#### 1. Ergonomic Persona & Form Factor
- **Grip Profile:** Precision ergonomic wand designed for relaxed 3-finger palming (index finger resting comfortably over the recessed bottom trigger, thumb naturally centered on the upper navigation rocker).
- **Neutral Angulation:** 18° downward inclination along the longitudinal axis matches the natural resting angle of the human carpal tunnel, preventing pronation strain.
- **Mass & Balance:** **52.0 grams**. Balanced 45% forward / 55% rearward to rest effortlessly against the thenar webspace.

#### 2. Dimensions & Mechanical Tolerances
- **Length:** 132.0 mm.
- **Max Width (Palm Grip):** 28.5 mm.
- **Min Neck Width (Index Rest):** 18.2 mm.
- **Max Height:** 24.0 mm.
- **Trigger Throw:** 1.4 mm pre-travel, 0.4 mm tactile snap.
- **Tolerances:** ±0.08 mm unibody seam alignment.

#### 3. Color, Material & Finish (CMF)
- **Top Unibody Spine:** CNC machined 6061-T6 aluminum alloy, shot-peened and anodized in Midnight Obsidian (L* 18, a* -0.4, b* -0.8).
- **Lower Grip Casing:** Dual-shot injection molded PC-ABS with overmolded soft-touch medical fluoroelastomer (Shore 55A hardness) featuring laser-etched micro-dot stippling.
- **Accent Ring:** Smoked PMMA light-guide with internal RGBW neo-pixel array (AirCursor Cyan signature #00e5ff).
- **Trigger Cap:** Magnesium AZ91D die-cast with micro-grooved anti-slip ridges.

#### 4. Sensor & Electrical Architecture
- **Primary Trigger:** Omron D2F subminiature mechanical micro-switch (0.74N actuation force, rated for 10 million cycles).
- **Thumb Rocker:** 5-way low-profile tactile navigation switch (Up, Down, Left, Right, Center Press) with aluminum keycap.
- **Stem Squeeze Sensors:** Dual lateral force-sensing strain gauge arrays (piezoresistive film, 0.2N to 5.0N continuous dynamic force curve, identical to AirPods Pro stem squeeze mechanics).
- **Orientation System:** 9-axis sensor fusion: TDK ICM-42688-P 6-axis IMU paired with an Asahi Kasei AK09918 3-axis geomagnetic sensor (provides driftless spatial orientation vectors).
- **Haptic Engine:** KEMET linear resonant actuator (LRA) along the spine providing rich haptic frequencies from 60 Hz to 240 Hz.
- **Power Subsystem:** 350 mAh rechargeable Li-Po cell; 94 hours active streaming; recessed USB-C connector at base + twin magnetic docking pads.

#### 5. AirCursor Interaction Modalities
- **Primary Click & Drag:** Index finger trigger pulls for instantaneous left-click; holding trigger locks drag operations while head pose moves the dragged window.
- **Lateral Stem Squeeze:** Squeezing the wand body between thumb and middle finger toggles AirCursor Tracking Pause / Resume with a dual-click haptic confirmation.
- **Spatial Laser Pointer:** Pointing the wand at the screen acts as an absolute spatial laser pointer, dynamically overriding head tracking whenever wand velocity exceeds 15°/s.
- **Thumb Rocker:** Up/Down adjusts screen zoom / volume; Left/Right cycles browser tabs or application windows.

---

### Concept 3: AirPebble Touch (Organic River-Stone Desk Puck)

```
             .-------------------------.
           /      [Frosted Glass Dome]   \    <-- Multi-Touch Capacitive Surface
          |     (3-Point Multi-Touch)     |
         +---------------------------------+
         | |====[Knurled Rotary Dial]====| |  <-- 6061-T6 Aluminum Dial (64 Detents)
         +---------------------------------+
          \   [Ceramic Base / PTFE Pads]   /
           '-----------------------------'
                [ PAW3395 Optical Flow ]
```

#### 1. Ergonomic Persona & Form Factor
- **Form Inspiration:** Organic, water-smoothed river pebble with an elliptical cross-section.
- **Dual-Mode Functionality:** Operates either resting flat on a mousepad/desk or cradled effortlessly in the palm like a tactile worry-stone.
- **Mass & Inertia:** **64.0 grams** (incorporates an internal brass ballast ring to provide stable desk grounding without accidental tipping).

#### 2. Dimensions & Mechanical Tolerances
- **Major Axis (Length):** 68.0 mm.
- **Minor Axis (Width):** 54.0 mm.
- **Apex Height:** 19.5 mm (gradual 12° dome slope).
- **Rotary Dial Width:** 4.2 mm knurled exposed crown rim.
- **Tolerances:** Glass-to-metal perimeter gap ≤ 0.10 mm.

#### 3. Color, Material & Finish (CMF)
- **Top Dome:** Chemically-strengthened Corning Gorilla Glass Victus with dual-sided acid-etched velvet matte finish (haptic silk feel, smudge-free oleophobic nano-coating).
- **Rotary Dial Crown:** Aerospace 6061 aluminum with 0.5 mm pitch diamond knurling, anodized in Raw Natural Silver or Space Graphite.
- **Lower Chassis:** Injection-molded zirconia-reinforced ceramic composite, providing high density, cool hand-feel, and scratch resistance.
- **Feet:** Four virgin-grade 0.8 mm PTFE curved glide skates.

#### 4. Sensor & Electrical Architecture
- **Multi-Touch Matrix:** Synaptics 36-channel mutual-capacitive sensor matrix laminated directly beneath the glass dome (detects 1, 2, and 3-finger gestures at 140 Hz).
- **Rotary Optical Encoder:** Custom magnetic Hall-effect 64-detent rotary encoder with configurable software detent stiffness.
- **Desk Optical Sensor:** PixArt PAW3395 gaming-grade optical sensor (26,000 DPI, 650 IPS tracking speed) embedded in the base for seamless transition to traditional mouse navigation.
- **Haptic Engine:** Dual balanced circular LRAs positioned beneath the glass dome to convey localized surface textures (e.g., clicking feel under finger contacts).
- **Power & Charging:** 450 mAh Li-Po cell; 120 hours active use; integrated Qi wireless charging coil (100% wireless sealed enclosure).

#### 5. AirCursor Interaction Modalities
- **Scrub & Calibrate:** Spinning the aluminum perimeter dial scrubs timelines (video/audio editing) or fine-tunes AirCursor head-tracking sensitivity on the fly.
- **Radial Gestures:** Swiping two fingers inward across the glass dome recenters the AirCursor pointer; tapping two fingers performs a middle-click.
- **Desktop/Air Hybrid:** When on desk, slide AirPebble to override head cursor instantly; when lifted, head tracking seamlessly re-engages while the puck serves as a palm controller.

---

### Concept 4: AirClip Mini (14g Eyewear / Collar Lapel Clip)

```
          .-------------------------.
         /  [Capacitive Tap/Swipe]   \   <-- High-Gloss Polycarbonate Pad
        |   =======================   |
        |   [ O ] Micro Status LED    |   <-- RGB Pill Indicator
        |   [ | ] Hardware Mute Slide |   <-- Micro Red Toggle Switch
        +-----------------------------+
        | \                         / |
        |  \--- Stainless Spring ---/ |   <-- 301 Stainless Steel Torsion Clip
        |       [Silicone Gripper]    |   <-- Non-Slip Eyewear / Fabric Clamp
        +-----------------------------+
```

#### 1. Ergonomic Persona & Form Factor
- **Mounting Versatility:** Ultra-compact clip engineered to anchor firmly to eyewear temples (prescription or sunglasses frames 1.2 mm to 4.5 mm thick), shirt lapels, collar bands, or hat brims.
- **Weight Target:** **14.0 grams** total weight (negligible mass creates zero temple sagging or frame twisting on prescription glasses).

#### 2. Dimensions & Mechanical Tolerances
- **Length:** 38.5 mm.
- **Width:** 14.2 mm.
- **Overall Thickness (including clip jaw):** 9.8 mm.
- **Clip Jaw Gap Range:** 0.8 mm (closed) to 5.2 mm (max spring deflection).
- **Tolerances:** ±0.05 mm precision alignment.

#### 3. Color, Material & Finish (CMF)
- **Top Enclosure:** Carbon-fiber reinforced polymer (CFRP) with exposed 3K twill weave finish, clearcoat UV-cured matte.
- **Clip Arm:** Heat-treated 301 full-hard stainless steel with PVD Black Titanium nitride coating.
- **Grip Teeth:** Overmolded 40A durometer silicone rubber ribbed pads to grip eyewear acetate/metal without marring.
- **Toggle Accent:** Anodized electric crimson red slide actuator.

#### 4. Sensor & Electrical Architecture
- **Auxiliary Head-Tracking IMU:** Bosch Sensortec BMI270 ultra-low-power 6-axis IMU (synchronized via BLE timestamping directly with AirCursor engine as a zero-camera orientation reference).
- **Capacitive Touch Face:** 3-zone capacitive electrode sensor along the outer CFRP housing for tap, double-tap, and linear swipe detection.
- **Hardware Toggle:** Micro SPST slide switch providing physical disconnect of pointer tracking (privacy / head-movement freedom toggle).
- **Haptic Feedback:** Subminiature coin-vibration motor (Ø 8 mm x 2 mm) emitting discreet buzzing pulses behind the ear.
- **Power & Battery:** 65 mAh micro lithium pouch cell; 28 hours continuous 100 Hz IMU transmission; magnetic 2-pin quick-dock charger.

#### 5. AirCursor Interaction Modalities
- **Zero-Camera Head Tracking:** When worn on glasses temples, AirClip Mini streams high-frequency 6-DOF head orientation vectors, allowing AirCursor to function flawlessly in pitch-black rooms or without any webcam.
- **Temple Tap Clicking:** Tapping index finger against the clip body triggers instant primary click without requiring any hand-held remote.
- **Lapel Swipe:** When clipped to a collar, swiping finger up/down adjusts scroll speed; double-tap locks drag.

---

### Concept 5: AirDeck Controller (Asymmetric Handheld Thumb-Deck)

```
        [ Shoulder Trigger L1 ]       [ Shoulder Trigger R1 ]
               \                             /
          .-----'---------------------------'-----.
         /   [=== OLED Status Display ===]         \
        /                                           \
       |      (O) Concave Thumb Trackpad             |  <-- 22mm Force Trackpad
       |          (Tactile Center Pip)               |
       |                                             |
       |      [A] [B] Tactile Profile Keys           |
       |                                             |
        \       /// Textured Palm Grip ///          /   <-- Asymmetric Ergonomic Swell
         '-----------------------------------------'
                     [ Lanyard / USB-C ]
```

#### 1. Ergonomic Persona & Form Factor
- **Form Inspiration:** Compact handheld thumb-deck combining the precision of an aerospace throttle controller with the accessibility of a modern gaming handheld.
- **Asymmetric Sculpting:** Contoured palm swell fits comfortably into the palm of either hand; index and middle fingers naturally wrap around the top shoulder triggers while the thumb sweeps across the trackpad.
- **Mass & Feel:** **68.0 grams**. Rigid magnesium-aluminum unibody provides dense, premium hand-feel.

#### 2. Dimensions & Mechanical Tolerances
- **Length:** 88.0 mm.
- **Width:** 46.0 mm.
- **Depth:** 22.0 mm (chassis thickness 13.5 mm; palm swell peak 22.0 mm).
- **Trackpad Diameter:** 22.0 mm concave disc (0.8 mm recess depth).
- **Trigger Travel:** 2.2 mm progressive resistance.

#### 3. Color, Material & Finish (CMF)
- **Top & Lower Chassis:** Die-cast and CNC-milled AZ91D Magnesium alloy, coated in electro-deposition Ceramic Matte White or Stealth Charcoal.
- **Trackpad Disc:** Textured PBT (polybutylene terephthalate) with micro-spherical concave depression and raised center tactile indexing pip.
- **Display Lens:** Smoked optical polycarbonate with anti-reflective AR coating.
- **Shoulder Triggers:** Dual-anodized deep cobalt blue aluminum triggers with micro-ribbed finger rests.

#### 4. Sensor & Electrical Architecture
- **Concave Thumb Trackpad:** 22mm Cirque capacitive glide sensor integrated with a center Hall-effect strain gauge (distinguishes soft touch from hard 2.0N click).
- **Shoulder Triggers:** Dual Kaihua low-profile micro-switches with silicone dampeners for near-silent 48 dB acoustic click.
- **Status OLED:** 0.49-inch monochrome white PMOLED display (64 x 32 pixels, 180 cd/m² brightness) displaying active profile, battery percentage, DPI, and connection status.
- **Motion Sensors:** TDK ICM-42688-P 6-axis IMU for motion tilt gestures (e.g., tilt forward to zoom).
- **Haptic Engine:** Dual high-bandwidth LRAs (X-axis and Z-axis) for independent trigger haptics and trackpad textures.
- **Power & Connectivity:** 500 mAh Li-Po cell; 82 hours continuous operation; USB-C fast charging + 2.4 GHz ultra-low-latency (sub-2ms) dongle and BLE 5.3.

#### 5. AirCursor Interaction Modalities
- **CAD & Productivity Navigation:** Left shoulder trigger locks primary click; right trigger executes secondary contextual actions; thumb trackpad executes multi-axis panning, rotation, and orbit commands in CAD/3D software.
- **Dynamic Profile Switching:** Quick-press profile keys toggle between "CAD Mode", "Web Browsing", "Gaming Deck", and "Media Presentation".
- **OLED Telemetry:** Gives instantaneous visual confirmation of AirCursor gesture status, active tracking mode, and latency metrics.

---

## 3. Cross-Concept Comparative CMF & Specification Matrix

| Metric / Parameter | Concept 1: AirRing Pro | Concept 2: AirWand Elite | Concept 3: AirPebble Touch | Concept 4: AirClip Mini | Concept 5: AirDeck |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Form Archetype** | Index-Finger Smart Ring | Handheld Spatial Wand | Desk / Palm River Stone | Eyewear / Lapel Clip | Handheld Asymmetric Deck |
| **Mass (Grams)** | 8.8 g | 52.0 g | 64.0 g | 14.0 g | 68.0 g |
| **Dimensions (mm)** | Ø 23.8 x 8.4 mm | 132 x 28.5 x 24.0 mm | 68.0 x 54.0 x 19.5 mm | 38.5 x 14.2 x 9.8 mm | 88.0 x 46.0 x 22.0 mm |
| **Primary Material** | Grade 5 Titanium + PEEK | 6061-T6 Alum + Fluoroelastomer | Gorilla Glass + Zirconia Ceramic | CFRP Composite + 301 Stainless | AZ91D Magnesium Alloy |
| **Finish & Texture** | Satin PVD + Diamond Chamfer | Bead-Blasted Anodized + Soft Touch | Velvet Matte Acid Etched + Knurled | 3K Twill Carbon Weave Clearcoat | Micro-Arc Ceramic Matte |
| **Primary Input** | Micro Trackball (PAT9125) | Omron Index Trigger Switch | Full-Surface Capacitive Dome | 3-Zone Capacitive Tap Pad | 22mm Concave Force Trackpad |
| **Secondary Input** | 360° Capacitive Ring Bezel | 5-Way Rocker + Squeeze Stem | 64-Detent Rotary Knurled Dial | Micro Hardware Mute Slide | Dual Shoulder Triggers (L1/R1) |
| **Sensor Suite** | 6-Axis IMU + Optical Flow | 9-Axis IMU (with Mag) + Strain | PAW3395 Optical + Cap Matrix | BMI270 6-Axis IMU + Cap | 6-Axis IMU + Strain + Cap |
| **Haptic Feedback** | Piezoelectric TDK PowerHap | Wideband KEMET LRA | Dual Localized Circular LRAs | Micro Eccentric Mass Buzzer | Dual Independent Multi-Axis LRAs |
| **Display / Accent** | Cyan Micro LED Ring | Cyan Emissive Perimeter Ring | Edge-Lit LED Ring Indicator | RGB Pill Status Indicator | 0.49" Monochrome White OLED |
| **Battery Life** | 38 Hours Active (24 mAh) | 94 Hours Active (350 mAh) | 120 Hours Active (450 mAh) | 28 Hours Active (65 mAh) | 82 Hours Active (500 mAh) |
| **Charging Method** | 2-Pin Magnetic Pogo Dock | USB-C + Magnetic Pogo Base | Qi Wireless Charging (5W) | 2-Pin Magnetic Pogo Cable | USB-C Port + Fast Charge |
| **Ideal Use Case** | All-day typing & casual browsing | Spatial presentation & VR/TV | Desk CAD scrub & audio mastering | Eyewear IMU fallback & stealth | Heavy CAD drafting & gaming |

---

## 4. Electrical Architecture, Wireless Protocols & Power Budgets

All five remote concepts utilize the Nordic Semiconductor nRF5340 / nRF52840 SoC family, providing:
- **Bluetooth 5.3 Low Energy (HOGP):** Standard Human Interface Device over GATT profile compatibility across Windows 11, macOS, Android TV, and Linux without custom driver installation.
- **AirCursor Ultra-Low Latency Channel (ULLC):** Custom 2.4 GHz packet protocol transmitting 16-byte telemetry packets at 200 Hz with sub-3.2 ms packet latency.
- **Power Optimization State Machine:**
  - *Active Streaming (200 Hz IMU + Touch):* 4.8 mA – 7.2 mA.
  - *Idle Sleep (After 5 seconds of inactivity):* 140 µA.
  - *Deep Sleep / Shelf State (After 10 minutes):* 3.8 µA (wakes via IMU motion interrupt threshold > 0.15g).

---

## 5. Integration with AirCursor Software Architecture

The remotes integrate directly into the existing `AirCursor_CrossPlatform` architecture:

```
+-----------------------------------------------------------------------------------+
|                           AIRCURSOR CORE ARCHITECTURE                             |
|                                                                                   |
|  [ WebCam / CV Pose ]                 [ AirCursor Physical Remote ]               |
|            |                                        |                             |
|            v                                        v                             |
|  +-------------------+                    +--------------------+                  |
|  |   MotionSample    |                    |  Hardware Remote   |                  |
|  |  (Head Kinematics)|                    |  (IMU/Track/Click) |                  |
|  +-------------------+                    +--------------------+                  |
|            |                                        |                             |
|            +-------------------+--------------------+                             |
|                                |                                                  |
|                                v                                                  |
|                   +--------------------------+                                    |
|                   |   Human-Input Arbiter    |                                    |
|                   |  - Physical Click Gate   |                                    |
|                   |  - Sub-Pixel Micro-Nudge |                                    |
|                   |  - Camera Loss Fallback  |                                    |
|                   +--------------------------+                                    |
|                                |                                                  |
|                                v                                                  |
|                   +--------------------------+                                    |
|                   |  PointerMapper & Action  |                                    |
|                   |     (OS Input Injection) |                                    |
|                   +--------------------------+                                    |
+-----------------------------------------------------------------------------------+
```

1. **Physical Click Arbitration:** When a hardware click is detected from the remote (e.g., AirWand trigger or AirRing trackball tap), dwell detection is immediately suppressed, eliminating false positives and reducing click latency to < 4 ms.
2. **Sub-Pixel Micro-Nudging:** When head tracking brings the cursor near a UI target, tiny thumb inputs from the AirRing trackball or AirDeck pad apply fine offset deltas without causing head jitter.
3. **Camera Loss Fallback:** If the user turns away from the webcam or lighting dims below 10 lux, the remote's onboard IMU smoothly takes over pointer rotation vectors until visual tracking is re-established.

