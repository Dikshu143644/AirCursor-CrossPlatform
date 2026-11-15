# AirCursor Physical Remote Hardware: Manufacturing & Engineering Dossier
**Document Reference**: `AC-ENG-MFG-2026-V1`  
**Revision**: `1.0.0 Production Release`  
**Classification**: Engineering & Tooling Specification  
**Associated 3D Assets**: `cad/models/` (`.blend`, `.glb`, `.obj`, `.stl`) | `cad/renders/` (`.png`)

---

## Executive Summary & Product Ecosystem

The AirCursor Physical Remote Product Suite provides 5 specialized, ultra-ergonomic hardware companions designed to bridge human intent with computer interaction across Windows, macOS, Linux, Android, and iOS. Each product is engineered for specific operational contexts—ranging from hands-free accessibility and ambient wearable computing to precision desktop navigation and mobile presentation control.

```
+==================================================================================================================+
| ID | Product Name       | Form Factor          | Mass  | Primary Controls              | Primary Sensors         |
+----+--------------------+----------------------+-------+-------------------------------+-------------------------+
| 01 | AirRing Pro        | Index-Finger Ring    | 8.8g  | Micro trackball, scroll bezel | 6-DoF IMU, Optical Flow |
| 02 | AirWand Elite      | Ergonomic Air Baton  | 52.0g | Dual trigger, 5-way rocker    | 9-DoF AHRS Fusion       |
| 03 | AirPebble Touch    | River-Stone Puck     | 64.0g | Frosted glass, knurled dial   | PAW3395 26k DPI + Gyro  |
| 04 | AirClip Mini       | Eyewear/Lapel Clip   | 14.0g | Crimson mute toggle, tap zone | 6-DoF IMU + Barometer   |
| 05 | AirDeck Controller | Asymmetric Deck      | 68.0g | Force trackpad, dual shoulder | Dual 6-DoF IMU + OLED   |
+==================================================================================================================+
```

All 5 devices share the unified **AirCursor 2.4GHz Low-Latency / BLE 5.3 Long-Range RF Architecture**, achieving sub-4ms input latency, 1000Hz polling rate in desktop/RF dongle mode, and battery endurance ranging from 18.5 hours to 60+ continuous active hours.

---

## Product 01: AirRing Pro (Wearable Smart Ring)

### 1.1 Mechanical Architecture & Dimensional Envelope
- **Form Factor**: Index-finger mounted ring with thumb-facing interaction pod.
- **Envelope**: Outer Diameter: $24.5\,\text{mm}$ | Width: $11.2\,\text{mm}$ | Wall Thickness: $1.6\,\text{mm}$ | Mass: $8.8\,\text{g}$.
- **Sizing System**: US Sizes 8 through 13 via snap-in biocompatible medical-grade liquid silicone rubber (LSR) inner contour liners (USP Class VI certified).
- **Control Pod**: Thumb-facing elevated pedestal housing a $4.2\,\text{mm}$ ceramic micro-optical trackball sphere and a circumferential 36-segment capacitive scroll ring bezel.
- **Charging & Docking**: Dual gold-plated beryllium copper (BeCu) pogo contacts on the inner perimeter with magnetic polarity keying (N52 neodymium magnet pair).

### 1.2 Material & CMF Specification
- **Outer Shell**: Grade 5 Titanium (`Ti-6Al-4V`), 5-axis CNC micro-milled, bead-blasted with $50\,\mu\text{m}$ zirconia beads, physical vapor deposition (PVD) Diamond-Like Carbon (DLC) coating (Surface hardness: $>2500\,\text{HV}$).
- **Optical Lens Bezel**: Sapphire crystal window with double-sided anti-reflective coating ($99.2\%$ transmission at $850\,\text{nm}$).
- **Inner Contact Liner**: Liquid Silicone Rubber (Shore 50A), hypoallergenic, sweat-resistant, IP68 rated hermetic seal.

### 1.3 Bill of Materials (BOM) — 10k Production Unit Run
| RefDes | Component / Subsystem | Manufacturer & MPN | Specifications | Unit Cost (USD) |
|:-------|:----------------------|:-------------------|:---------------|:----------------|
| U1 | Main Microcontroller | Nordic Semi `nRF5340` | Dual-core ARM Cortex-M33, BLE 5.3, 1MB Flash | \$3.15 |
| U2 | 6-Axis IMU | Bosch Sensortec `BMI270` | 16-bit ultra-low power 6-axis IMU, $0.85\,\text{mA}$ active | \$1.20 |
| U3 | Optical Flow Tracker | PixArt `P3360-mini` | Micro-die optical navigation sensor, 800 DPI | \$1.85 |
| U4 | Power Management IC | TI `BQ25120A` | 700nA quiescent current buck converter & LiPo charger | \$0.95 |
| B1 | Rechargeable LiPo Cell | Renata / ATL `CP0811` | $3.7\,\text{V}$, $38\,\text{mAh}$ custom curved cell ($18.5\text{h}$ runtime) | \$2.40 |
| M1 | Optical Trackball Module | Custom Swiss Jewel | $4.2\,\text{mm}$ synthetic ruby sphere, PTFE suspension rings | \$1.50 |
| PCB | Rigid-Flex Substrate | AT&S 4-Layer | 4-layer polyimide flexible interconnect, immersion gold | \$1.80 |
| ENCL | Titanium Outer Shell | Custom CNC | Grade 5 Titanium, DLC PVD coated finish | \$6.50 |
| -- | Passive, connectors, magnets | Various | N52 magnets, BeCu pogo contacts, passives | \$1.20 |
| **TOTAL** | **AirRing Pro BOM (COGS)** | | **Estimated Ex-Factory Cost** | **\$20.55** |

### 1.4 3D Printing & Rapid Prototyping Parameters
- **SLA Photopolymer (Recommended for sizing verification)**:
  - Material: Formlabs Rigid 10K Resin (Glass-filled, high stiffness, $10\,\text{GPa}$ flexural modulus).
  - Layer Thickness: $25\,\mu\text{m}$ ($0.025\,\text{mm}$).
  - Print Orientation: $45^\circ$ angle on ring axis to eliminate layer stair-stepping on internal finger cylinder.
  - Post-Curing: 60 minutes at $70^\circ\text{C}$ under $405\,\text{nm}$ UV light.
- **FDM Printing (Draft prototypes)**:
  - Material: PETG or Carbon Fiber Polycarbonate (PC-CF).
  - Nozzle: $0.2\,\text{mm}$ high-precision nozzle, $0.08\,\text{mm}$ layer height, $100\%$ concentric infill.

---

## Product 02: AirWand Elite (Ergonomic Air Baton)

### 1.1 Mechanical Architecture & Dimensional Envelope
- **Form Factor**: Contoured handheld air baton with trigger grip and thumb control cluster.
- **Envelope**: Length: $132.0\,\text{mm}$ | Grip Diameter: $24.5\,\text{mm}$ tapering to $20.0\,\text{mm}$ | Head Width: $26.8\,\text{mm}$ | Mass: $52.0\,\text{g}$.
- **Ergonomics**: $12^\circ$ forward neutral-wrist tilt angle prevents carpal tunnel stress during prolonged air mouse interaction.
- **Control Surfaces**:
  - Index Finger: Two-stage mechanical micro-switch trigger (Stage 1: Soft hover target lock at $0.8\,\text{N}$; Stage 2: Crisp mechanical click at $1.8\,\text{N}$).
  - Thumb Cluster: 5-way tactile rocker switch with center push-click.
  - Bilateral Palm Zones: Dual capacitive force-sensitive strain pads for squeeze-to-drag, pan, or zoom.
  - Nose Cone: Flush infrared LED ring emitter ($850\,\text{nm}$) for sub-millimeter optical desk camera tracking.

### 1.2 Material & CMF Specification
- **Primary Chassis**: Two-piece split unibody in Aerospace Aluminum `7075-T6`, CNC machined with high-speed toolpaths, Type III Hard Anodized (Mil-A-8625, Class 2, Charcoal Black, $45\,\mu\text{m}$ thickness).
- **Grip Overmold**: Biocompatible Thermoplastic Polyurethane (TPU Shore 65A) with micro-dot laser texture (VDI 3400 Ref 27) for non-slip grip.
- **Trigger Keycap**: Polyether Ether Ketone (PEEK) for thermal stability and zero play.

### 1.3 Bill of Materials (BOM) — 10k Production Unit Run
| RefDes | Component / Subsystem | Manufacturer & MPN | Specifications | Unit Cost (USD) |
|:-------|:----------------------|:-------------------|:---------------|:----------------|
| U1 | Main Microcontroller | Nordic Semi `nRF5340` | Dual-core ARM Cortex-M33, 2.4GHz + BLE | \$3.15 |
| U2 | 9-Axis AHRS IMU | CEVA / Hillcrest `BNO085` | 9-DoF Sensor Hub with embedded sensor fusion | \$4.80 |
| SW1 | Two-Stage Trigger | Omron `D2LS-11` | Sealed micro switch, 5,000,000 cycle rating | \$0.75 |
| SW2 | 5-Way Thumb Rocker | Alps Alpine `SKQUAAA010` | 5-position directional navigation switch | \$1.10 |
| S1-S2 | Squeeze Force Sensors | Interlink `FSR-400` | Thin polymer thick film force sensing resistors | \$1.60 |
| ACT1 | Haptic LRA Motor | AAC Technologies `1030` | Linear resonant actuator with crisp $170\,\text{Hz}$ clicks | \$1.15 |
| B1 | Rechargeable LiPo Battery | EEMB `LP502035` | $3.7\,\text{V}$, $320\,\text{mAh}$ prismatic cell ($42.0\text{h}$ runtime) | \$2.10 |
| CHASSIS| Aluminum Shell Set | 7075-T6 CNC Machined | Anodized Charcoal Black, bead-blasted | \$8.40 |
| -- | Optics, lens, wiring, screws | Various | IR LED, PMMA diffuser, stainless Torx T5 fasteners | \$1.45 |
| **TOTAL** | **AirWand Elite BOM (COGS)** | | **Estimated Ex-Factory Cost** | **\$24.50** |

### 1.4 3D Printing & Rapid Prototyping Parameters
- **SLA Photopolymer**:
  - Material: Formlabs Tough 2000 Resin (Simulates ABS, high elongation and impact resistance).
  - Layer Thickness: $50\,\mu\text{m}$.
  - Print Orientation: Upright at $20^\circ$ incline with base supports on lanyard eyelet.
- **FDM Printing**:
  - Material: Polycarbonate-ABS (PC-ABS) or PLA-Plus.
  - Settings: 4 perimeter walls, 35% gyroid infill, $0.12\,\text{mm}$ layer height, organic tree supports under trigger guard.

---

## Product 03: AirPebble Touch (River-Stone Palm & Desk Puck)

### 1.1 Mechanical Architecture & Dimensional Envelope
- **Form Factor**: Smooth river-stone ergonomic palm/desk puck with multi-touch frosted glass dome and perimeter rotary dial.
- **Envelope**: Length: $68.0\,\text{mm}$ | Width: $56.0\,\text{mm}$ | Height: $22.4\,\text{mm}$ | Mass: $64.0\,\text{g}$.
- **Dual-Mode Operation**:
  - **Desk Mode**: PAW3395 26,000 DPI flagship optical sensor with 650 IPS tracking on any desk surface; PTFE zero-friction glide skates.
  - **Air Mode**: Auto-engages when optical lift-off distance exceeds $2.5\,\text{mm}$. The puck transitions instantly into 6-axis gyro air-mouse mode with haptic confirmation.
- **Control Surfaces**:
  - Frosted Glass Dome: Capacitive multi-touch surface supporting 1-finger trackpad movement, 2-finger inertia scrolling, and 3-finger app switching.
  - Knurled Rotary Ring: 6061-T6 aluminum dial with 24 magnetic detents per revolution and push-down middle click for timeline scrub, volume, or brush sizing.

### 1.2 Material & CMF Specification
- **Top Touch Surface**: Chemically strengthened Corning Gorilla Glass Victus 2, $0.8\,\text{mm}$ thickness, 3D CNC hot-bent contour, acid-etched anti-glare finish (Surface roughness Ra $0.4\,\mu\text{m}$), oleophobic anti-fingerprint coating.
- **Dial Wheel**: CNC milled Aluminum 6061 with diamond knurl pattern (DIN 82-RGE $0.8\,\text{mm}$ pitch), bright-dip clear anodized.
- **Base Enclosure**: Die-cast Magnesium alloy (`AZ91D`) for lightweight structural rigidity, electrodeposition e-coat matte titanium gray.
- **Skates**: $100\%$ Virgin Grade Polytetrafluoroethylene (PTFE), curved edges with $0.8\,\text{mm}$ thickness.

### 1.3 Bill of Materials (BOM) — 10k Production Unit Run
| RefDes | Component / Subsystem | Manufacturer & MPN | Specifications | Unit Cost (USD) |
|:-------|:----------------------|:-------------------|:---------------|:----------------|
| U1 | Main Microcontroller | Nordic Semi `nRF5340` | Dual-core ARM Cortex-M33, 1000Hz USB/RF | \$3.15 |
| U2 | Flagship Optical Sensor | PixArt `PAW3395` | 26,000 DPI, 650 IPS, 50G acceleration | \$5.50 |
| U3 | 6-Axis Gyro/Accel | STMicro `LSM6DSOX` | Ultra-low noise 6-axis IMU with embedded FSM | \$1.65 |
| U4 | Multi-Touch Controller | Microchip `CAP1298` | 8-channel capacitive touch sensing controller | \$1.20 |
| ACT1-2 | Dual Haptic Actuators | TDK `PowerHap 2.5G` | Piezoelectric ultra-crisp haptic actuators (2.5G peak) | \$3.20 |
| B1 | Rechargeable LiPo Battery | Grepow `LP602535` | $3.7\,\text{V}$, $450\,\text{mAh}$ pouch cell ($60.0\text{h}$ runtime) | \$2.60 |
| GLASS | 3D Frosted Glass Dome | Corning Victus 2 | Custom 3D hot-bent, acid etched, oleophobic | \$5.80 |
| BASE | Magnesium Die-Cast Base | AZ91D Magnesium | E-coated, CNC post-machined skate recesses | \$4.10 |
| DIAL | Aluminum Rotary Ring | 6061-T6 CNC | Diamond knurl, neodymium magnetic detent ring | \$2.30 |
| -- | PTFE skates, USB-C port, FPC | Various | 24-pin USB-C receptacle, gold pogo contacts | \$1.90 |
| **TOTAL** | **AirPebble Touch BOM (COGS)** | | **Estimated Ex-Factory Cost** | **\$31.40** |

### 1.4 3D Printing & Rapid Prototyping Parameters
- **SLA Photopolymer**:
  - Material: Formlabs Clear Resin (Polished to optical clarity and frosted with 1000-grit wet sanding for the glass dome replica); Rigid 10K for the internal core chassis.
  - Layer Thickness: $50\,\mu\text{m}$.
- **FDM Printing**:
  - Material: PLA-CF or ABS for base; TPU for non-slip feet testing.

---

## Product 04: AirClip Mini (Glasses & Lapel Collar Clip)

### 1.1 Mechanical Architecture & Dimensional Envelope
- **Form Factor**: Featherweight clamp-on clip for spectacle frames or shirt collar lapels.
- **Envelope**: Length: $38.0\,\text{mm}$ | Width: $14.5\,\text{mm}$ | Depth: $12.0\,\text{mm}$ | Mass: $14.0\,\text{g}$.
- **Retention Clamp**: Dual-tine spring-tempered Grade 5 Titanium clip arm lined with soft Santoprene rubber to securely grip glasses frames from $1.5\,\text{mm}$ to $6.0\,\text{mm}$ thickness with zero scratching.
- **Privacy Mute Hardware Switch**: Crimson anodized sliding toggle switch with positive mechanical detent. Disconnects IMU power rail at the hardware level, guaranteeing zero telemetry transmission when muted.
- **Outer Tap Surface**: Capacitive gesture strip for single-tap left click, double-tap right click, and long-press dwell activation.

### 1.2 Material & CMF Specification
- **Main Housing**: Glass-fiber reinforced Polycarbonate (`PC+20%GF`), ultrasonic welded hermetic seal, soft-touch matte finish (Pantone Cool Gray 11C).
- **Mute Switch Toggle**: Aerospace Aluminum 6061-T6, anodized Crimson Red (Pantone 186C), fine cross-hatch knurling.
- **Clip Arm**: Spring-tempered Titanium alloy wire (`Ti-15V-3Cr-3Sn-3Al`) with black PVD finish and overmolded Santoprene grip tips.

### 1.3 Bill of Materials (BOM) — 10k Production Unit Run
| RefDes | Component / Subsystem | Manufacturer & MPN | Specifications | Unit Cost (USD) |
|:-------|:----------------------|:-------------------|:---------------|:----------------|
| U1 | Main Microcontroller | Nordic Semi `nRF52840` | ARM Cortex-M4, BLE 5.3, ultra-low power | \$2.40 |
| U2 | 6-Axis Motion IMU | TDK InvenSense `ICM-42688-P` | Ultra-low noise 6-axis IMU, $0.88\,\text{mA}$ | \$1.45 |
| U3 | Precision Barometer | Bosch `BMP581` | Micro-barometric pressure sensor for pitch aiding | \$1.10 |
| SW1 | Hardware Privacy Switch | C&K `JS202011SCQN` | Sub-miniature DPDT sliding switch (cuts IMU power) | \$0.65 |
| B1 | Rechargeable LiPo Battery | Renata `ICP401220` | $3.7\,\text{V}$, $85\,\text{mAh}$ micro pouch cell ($24.0\text{h}$ runtime) | \$1.80 |
| CLIP | Titanium Wire Clip Arm | Custom Wire Form | Titanium spring alloy, overmolded tips | \$1.40 |
| ENCL | PC+GF Housing Set | Injection Molded | Mold-Tech MT-11010 fine texture, ultrasonic weld | \$1.90 |
| -- | Status RGB LED, contacts, FPC | Various | Multi-color LED, BeCu gold contacts, passives | \$0.90 |
| **TOTAL** | **AirClip Mini BOM (COGS)** | | **Estimated Ex-Factory Cost** | **\$11.60** |

### 1.4 3D Printing & Rapid Prototyping Parameters
- **SLA Photopolymer**:
  - Material: Formlabs Tough 1500 Resin (Simulates polypropylene, high spring fatigue resistance for clip testing).
  - Layer Thickness: $25\,\mu\text{m}$.
  - Orientation: Horizontal with clip opening angled upward at $30^\circ$.

---

## Product 05: AirDeck Controller (Handheld Asymmetric Thumb-Deck)

### 1.1 Mechanical Architecture & Dimensional Envelope
- **Form Factor**: Asymmetric thumb-deck controller designed for one-handed presentation, accessibility, and desktop media control.
- **Envelope**: Length: $88.0\,\text{mm}$ | Width: $48.0\,\text{mm}$ | Thickness: $19.5\,\text{mm}$ | Mass: $68.0\,\text{g}$.
- **Display & Interface**:
  - 0.49-inch monochrome OLED display ($64\times 32$ pixels, SSD1306 driver) displaying real-time tracking mode, battery percentage, cursor sensitivity, and active profile.
  - Concave force-sensitive thumb trackpad ($22.0\,\text{mm}$ diameter) with continuous pressure sensing for variable-speed cursor navigation.
  - Dual tactile shoulder triggers (L1 / R1) positioned for index and middle finger activation.
  - Power / Mode selection rocker on bottom chamfer.

### 1.2 Material & CMF Specification
- **Top & Bottom Housing**: High-impact Polycarbonate-ABS (`SABIC Cycoloy C2950`), flame retardant (UL94 V-0), fine spark-eroded texture (VDI 24, Space Gray finish).
- **Shoulder Bumpers**: Polyoxymethylene (`POM / Delrin 500P`) for low friction and crisp, repeatable switch actuation.
- **OLED Window**: Optical-grade Polymethyl Methacrylate (PMMA) with smoke tint ($85\%$ optical transmission).

### 1.3 Bill of Materials (BOM) — 10k Production Unit Run
| RefDes | Component / Subsystem | Manufacturer & MPN | Specifications | Unit Cost (USD) |
|:-------|:----------------------|:-------------------|:---------------|:----------------|
| U1 | Main Microcontroller | Nordic Semi `nRF5340` | Dual-core ARM Cortex-M33, 128MHz + 64MHz | \$3.15 |
| U2-U3 | Dual 6-Axis IMUs | 2x STMicro `LSM6DSOX` | Differential orientation cancellation pair | \$3.30 |
| DISP | 0.49" Monochrome OLED | WiseChip `UG-6432` | $64\times 32$ dots, I2C interface, $0.05\,\text{W}$ consumption | \$2.80 |
| FSR | Force-Sensing Trackpad | Interlink `FSR-402` | $22\,\text{mm}$ circular force sensing active area | \$1.90 |
| SW1-2 | Shoulder Micro-Switches | 2x Omron `D2LS-21` | Low profile tactile switches (5M cycle rating) | \$1.50 |
| ACT1-2 | Dual LRA Haptic Motors | 2x AAC `1020` | Dual independent left/right linear resonant actuators | \$2.10 |
| B1 | Rechargeable LiPo Battery | Sunpower `LP702540` | $3.7\,\text{V}$, $500\,\text{mAh}$ pouch cell ($50.0\text{h}$ runtime) | \$2.80 |
| ENCL | PC-ABS Housing Set | Injection Molded | Space Gray VDI 24 finish, brass heat-set inserts | \$3.60 |
| -- | PMMA window, screws, USB-C | Various | Tinted display lens, Torx T5 screws, USB-C port | \$1.75 |
| **TOTAL** | **AirDeck Controller BOM (COGS)** | | **Estimated Ex-Factory Cost** | **\$22.90** |

### 1.4 3D Printing & Rapid Prototyping Parameters
- **SLA Photopolymer**:
  - Material: Formlabs Black Resin or Grey Pro Resin.
  - Layer Thickness: $50\,\mu\text{m}$.
- **FDM Printing**:
  - Material: Carbon Fiber PLA (PLA-CF) or PETG.
  - Settings: $0.16\,\text{mm}$ layer height, 3 perimeter walls, 30% gyroid infill, support under shoulder bumper recesses.

---

## Universal Manufacturing Guidelines & Quality Standards

### 1. Tooling & Injection Molding Design Rules
- **Draft Angles**: Minimum $1.5^\circ$ on all vertical surfaces; $2.5^\circ$ for surfaces featuring EDM texture deeper than VDI 24.
- **Wall Thickness Uniformity**: Maintain nominal wall thickness within $\pm 10\%$ across each part to eliminate sink marks and differential shrinkage warpage:
  - AirRing Pro (Silicon liner): $1.20\,\text{mm}$ nominal.
  - AirWand Elite: $1.80\,\text{mm}$ nominal.
  - AirPebble Touch: $2.00\,\text{mm}$ nominal.
  - AirClip Mini: $1.50\,\text{mm}$ nominal.
  - AirDeck Controller: $1.75\,\text{mm}$ nominal.
- **Ultrasonic Welding Energy Directors**: Continuous $90^\circ$ triangular energy director ridge ($0.6\,\text{mm}$ height) along mating perimeter with flash traps for clean hermetic joint lines.

### 2. Regulatory Compliance & Environmental Standards
- **Electromagnetic Compatibility**:
  - FCC Part 15 Subpart C Section 15.247 (USA)
  - CE-RED Directive 2014/53/EU (European Union)
  - TELEC / MIC Certification (Japan)
  - SRRC (China)
- **Battery Safety & Transportation**:
  - UN 38.3 Lithium Battery Transport Testing (Thermal shock, vibration, overcharge, external short circuit)
  - IEC 62133-2 Secondary cells safety compliance
  - UL 1642 / UL 2054 Consumer battery standard
- **Environmental & Hazardous Materials**:
  - RoHS 3 Directive (EU 2015/863) 10 restricted substances compliant
  - WEEE Directive (2012/19/EU) compliant take-back labeling
  - REACH EC No 1907/2006 SVHC screening $<0.1\%\,\text{w/w}$
  - ISO 10993-5 / 10993-10 Cytotoxicity and skin irritation compliance for wearable surfaces (AirRing Pro and AirClip Mini)

---

## 3D CAD Production Deliverables Manifest

All 5 physical products have their complete 3D geometry generated, validated, and archived within the repository:

```
cad/models/
├── concept_1_airring_pro.blend          [Blender 5.1 native scene, materials, lights]
├── concept_1_airring_pro.glb            [glTF 2.0 WebGL-optimized PBR asset]
├── concept_1_airring_pro.obj            [Wavefront OBJ universal geometry]
├── concept_1_airring_pro.stl            [3D Print-ready binary manifold STL]
├── concept_2_airwand_elite.blend        [Blender 5.1 native scene]
├── concept_2_airwand_elite.glb          [glTF 2.0 WebGL asset]
├── concept_2_airwand_elite.obj          [Wavefront OBJ asset]
├── concept_2_airwand_elite.stl          [3D Print-ready binary manifold STL]
├── concept_3_airpebble_touch.blend      [Blender 5.1 native scene]
├── concept_3_airpebble_touch.glb        [glTF 2.0 WebGL asset]
├── concept_3_airpebble_touch.obj        [Wavefront OBJ asset]
├── concept_3_airpebble_touch.stl        [3D Print-ready binary manifold STL]
├── concept_4_airclip_mini.blend         [Blender 5.1 native scene]
├── concept_4_airclip_mini.glb           [glTF 2.0 WebGL asset]
├── concept_4_airclip_mini.obj           [Wavefront OBJ asset]
├── concept_4_airclip_mini.stl           [3D Print-ready binary manifold STL]
├── concept_5_airdeck_controller.blend   [Blender 5.1 native scene]
├── concept_5_airdeck_controller.glb     [glTF 2.0 WebGL asset]
├── concept_5_airdeck_controller.obj     [Wavefront OBJ asset]
└── concept_5_airdeck_controller.stl     [3D Print-ready binary manifold STL]
```

### Photorealistic Renders
```
cad/renders/
├── concept_1_airring_pro.png            [1280x720 Cycles studio render]
├── concept_2_airwand_elite.png          [1280x720 Cycles studio render]
├── concept_3_airpebble_touch.png        [1280x720 Cycles studio render]
├── concept_4_airclip_mini.png           [1280x720 Cycles studio render]
└── concept_5_airdeck_controller.png     [1280x720 Cycles studio render]
```
