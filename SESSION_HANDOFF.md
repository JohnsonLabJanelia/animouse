# AniMouse Session Handoff — Complete Project Context

Use this as your opening prompt in a new Claude Code session in the animouse repo.

---

## WHO I AM

I'm Rob Johnson (johnsonr), researcher at HHMI Janelia Research Campus. I lead the Johnson Lab. I build scientific software in C++ and Python, primarily using Claude Code. My major projects:

- **RED** (`~/src/red`): GPU-accelerated 3D multi-camera keypoint labeling tool (C++/Metal/CUDA, 32K+ LOC). Has MuJoCo IK integration, rodent and fruitfly body models built in. Preparing for biorxiv preprint.
- **GREEN** (`~/src/green`): ImGui data analysis dashboard for rat behavioral experiments. Paper nearly complete: "Mixed guidance laws govern interception steering in rats."
- **AniMouse** (this repo, `~/src/animouse`): Blender tools for the mouse biomechanical model. Just created.

I prefer terse communication and work fast. I target Nature/Nature Methods.

---

## THE PROJECT

We are building the most comprehensive mouse musculoskeletal atlas and biomechanical model to date, as part of the **AniBody project team at Janelia** (https://github.com/janelia-anibody). The organization has repos for fruitfly, mouse, zebrafish, and shared mujoco_utils. 21 team members.

### Pipeline
1. **MicroCT imaging** — Xradia VersaXRM 730. Two mice scanned. Mouse 1: high-res arm, leg, head (4x objective, individual muscle fibers visible). Mouse 2: whole body 70hr scan (0.4x objective). Combined into 4 datasets.
2. **PTA staining** — Minimally invasive perfusion technique (small hole below rib cage in abdomen to preserve chest musculature, possibly novel). 6-8 week perfusion, then 8-week passive PTA soaking.
3. **Paintera segmentation** — All done by Igor Siwanowicz (one person, ~6 months). Igor is the same person on the flybody Nature paper. Uses Paintera from Stephan Saalfeld's lab at Janelia.
4. **Blender model** — Igor builds the atlas and rigs it. File: `~/anibodymouse/claude_mouse/claude_mouse.blend` (205MB, Blender 4.1 format, opens fine in 5.0.1).
5. **MuJoCo export** — Via dm_control pipeline (same as janelia-anibody/fruitfly repo). Collaborators at Salk have begun rigging shoulder/arm in MuJoCo.
6. **Imitation learning** — Same PPO pipeline as Mimic-MJX. Hill-type muscles. Collaborators report our mouse arm uses LESS ENERGY than the mimic-mjx arm for the same reaching movements due to more accurate geometry.

### Blender Model Details (claude_mouse.blend)
- **586 objects** (583 meshes, 1 armature, 1 camera, 1 empty)
- **16.7M evaluated vertices**, 2.56M base vertices, 2.6M faces
- **47 collections**, 34 materials, 68 armature bones
- **File format:** Blender 4.1 (DO NOT re-save in 5.0 format — Igor needs 4.1 compatibility)

Tissue breakdown:
- bone: 280 meshes
- muscle: 182 meshes
- tendon/ligament: 97 meshes
- connective tissue: 8, cartilage: 3, eye: 3, kidney: 2, retina: 2
- CNS: 1, gastrointestinal: 1, tongue: 1, urinary: 1, cardiac: 1, vasculature: 1

Laterality: 363 midline, 118 right, 102 left

Key structures:
- Full spine: C1-C7, T1-T13, L1-L6, sacrum, CA1-CA30
- All ribs (33 meshes), skull, mandibles, hyoid, teeth
- Arm: 43 bones per side + claws. Leg: femur through phalanges + sesamoids + patella
- ~170 muscle meshes + 35+ arm tendons + shoulder tendons
- Muscles predominantly RIGHT side (left-side muscle collections mostly empty — symmetrization pending)
- Organs: heart, kidneys, bladder, intestine, CNS, vasculature, tongue, eyes
- Armature: right forelimb IK rig with muscle origin-insertion bone pairs (Pectoralis major, Serratus anterior, Acromiotrapezius, Levator claviculae, etc.)
- L-R bone symmetry COMPLETE. Muscle symmetrization NOT YET DONE.

Many meshes have `Retopo_` prefix (retopologized from scan data). These need proper anatomical names.

### Blender Units
- Internal units are METERS. Display says "centimeters" but that's just display.
- Convert to mm: multiply by 1000
- Camera clip_start MUST be 0.001 (1mm) or small objects won't render (default 0.1m = 100mm clips them)

### Collaborators
- **Eiman Azim & Talmo Pereira** (Salk Institute): co-authors on this paper. Contributing Figure 5 (reaching task). Have 3D kinematics mouse reaching data. Have imitation learning pipeline (mimic-mjx). Using Hill-type muscles. Same PPO pipeline.
- **Igor Siwanowicz**: all Paintera segmentation and Blender work. On Blender 4.1 or 4.2. Needs GitHub account. Also co-author on flybody Nature paper.
- **Srinivas Turaga group** at Janelia: overlaps with flybody authors.

---

## THE PAPER

**Target:** bioRxiv preprint by **April 28, 2026** (27 days from April 1)
**Journal:** Nature or Nature Methods
**Working title:** "A comprehensive musculoskeletal atlas and biomechanical model of the laboratory mouse"

### Scope
The whole-body atlas + functional trainable biomechanical model is the product. The reaching task is an example use case demonstrating the model's utility. Goal: transform how 3D pose tracking and biomechanical modeling is done for mice.

### Release plan
Will release: all imaging data, Blender atlas, rigged Blender model, MuJoCo model, trained NN controllers.

### Five Figures

**Figure 1: MicroCT Imaging Pipeline**
- (a) Minimally invasive PTA perfusion technique diagram
- (b) Protocol timeline: 6-8 week perfusion + 8-week passive PTA soak
- (c) Whole-body scan (0.4x, 70hr) volume rendering
- (d) High-res regional scans (4x) — head, arm, leg, individual muscle fibers
- (e) Multi-scale composite: whole body → arm → muscle fibers
- (f) Resolution comparison vs. Gilmer et al. / MausSpAun

**Figure 2: 3D Volumetric Segmentation**
- (a) Paintera workflow screenshots
- (b) Exploded anatomy — color-coded bones, muscles, tendons, ligaments
- (c) Atlas statistics (structure counts by category)
- (d) Forelimb detail with anatomical labels
- (e) Comparison to anatomical references
- (f) Coverage comparison vs. Gilmer (forelimb only), MausSpAun (50 muscles)

**Figure 3: Blender Atlas and Biomechanical Rigging**
- (a) Full mouse model renders (dorsal, ventral, lateral)
- (b) Skeletal system with L-R symmetry
- (c) Muscular system overlay
- (d) Rigging hierarchy, DOFs, IK chains
- (e) Forelimb muscle origin-insertion sites, tendon routing
- (f) L-R symmetrization validation

**Figure 4: MuJoCo Biomechanical Simulation**
- (a) Export pipeline: Blender → dm_control → MJCF XML → MuJoCo
- (b) MuJoCo visualization side-by-side with Blender
- (c) Hill-type muscle actuator specs
- (d) Passive dynamics validation
- (e) DOF/muscle comparison table vs. flybody, Gilmer, MausSpAun, MyoSuite
- (f) Open-source model structure

**Figure 5: Imitation Learning and Scientific Discovery** (Azim/Pereira contribute this)
- (a) Pipeline: 3D kinematics → stac-mjx → track-mjx → learned controller
- (b) Head-fixed reaching task setup
- (c) Learned vs. real reaching trajectories
- (d) KEY RESULT: energy comparison — our model vs. mimic-mjx arm
- (e) Predicted muscle activation patterns
- (f) What accurate geometry reveals about motor control

### Timeline
- Week 1 (Apr 1-7): Finalize Blender model for figures. Render Fig 1-3. Start Methods.
- Week 2 (Apr 8-14): MuJoCo export. Render Fig 4. Results for Fig 1-3.
- Week 3 (Apr 15-21): Imitation learning results from Salk. Fig 5. Results 4-5. Discussion.
- Week 4 (Apr 22-28): Full draft. Co-author review. Submit.

---

## RELATED WORK

### Most important references
1. **Vaxenburg et al. Nature 2025** — "Whole-body physics simulation of fruit fly locomotion." Same Janelia/Turaga team. 67 rigid bodies, 102 DOFs, NO muscles. Torque/position actuators. MuJoCo. RL via DMPO. Our methodological template. Code: github.com/TuragaLab/flybody
2. **Mimic-MJX** (Zhang, Yang, Pereira, Azim et al., arXiv 2511.21848) — GPU-parallelized imitation learning. stac-mjx (inverse kinematics) + track-mjx (PPO RL). Our collaborators' pipeline. Demo: mimic-mjx.talmolab.org
3. **Gilmer et al. 2024** (bioRxiv 10.1101/2024.09.05.611289) — First physiological mouse forelimb biomechanical model. OpenSim/MuJoCo. Most direct anatomical competitor.
4. **MausSpAun** (Mathis Lab, EPFL, bioRxiv 10.1101/2024.09.11.612513) — 50-muscle mouse forelimb + neural recordings. Neuroscience-focused. Code unreleased. mausspaun.org
5. **MyoSuite** (sites.google.com/view/myosuite, github.com/MyoHub/myosuite) — Musculoskeletal simulation benchmark. Hill-type muscles in MuJoCo. Human-focused but architecture transferable.
6. **dm_control** (github.com/google-deepmind/dm_control) — MuJoCo Python bindings. Our export pipeline. Has dm_control.mjcf for programmatic model building.
7. **uSim** (Almani et al. 2024, bioRxiv 10.1101/2024.02.02.578628) — Framework connecting RNN controllers to musculoskeletal models via RL.

### Our key differentiators
1. Most comprehensive mouse musculoskeletal model (whole body, not just forelimb)
2. MicroCT at 4x resolves individual muscle fibers
3. Possibly novel minimally invasive PTA perfusion technique
4. Functional physics-simulatable model, not just atlas
5. Energy efficiency: more accurate geometry → more efficient motor solutions
6. Complete open-source release of everything

---

## WHAT WE'VE BUILT SO FAR IN THIS REPO

### Repository structure (~/src/animouse/)
```
animouse/              # Blender add-on
  __init__.py          # AniMouse sidebar panel (3 operators)
  compat.py            # Blender 4.1/5.0 compatibility (EEVEE name, node inputs)
  tissue_types.py      # MATERIAL_TO_TISSUE mapping, TISSUE_COLORS palette, helpers
  mesh_metadata.py     # Geometric extraction (volume, SA, bbox, COM) + CSV/JSON export
  render_catalog.py    # Isolated mesh rendering in temporary scene
scripts/
  batch_render.py      # CLI batch rendering
  extract_catalog.py   # CLI metadata extraction
```

### Technical details discovered during development
- Blender `--background` mode: EEVEE works for rendering but had issues with `hide_render` for object isolation. Solution: create a fresh temporary scene, copy evaluated mesh into it, render, cleanup. This avoids all visibility/collection issues.
- EEVEE engine name: `"BLENDER_EEVEE"` in 5.0, was `"BLENDER_EEVEE_NEXT"` during 4.2 transition. The compat.py module handles this by checking enum items.
- Camera clip_start: DEFAULT IS 0.1m (100mm). Most mouse body parts are <20mm, so camera positioned at 5x max_dim is often <100mm from object. MUST set clip_start=0.001.
- Unit conversion: Blender internal = meters. Display says "centimeters" but that's cosmetic. Multiply by 1000 for mm, by 1e9 for mm³ volume, by 1e6 for mm² area.
- The .blend file is 4.1 format. The header byte `401` confirms this. Do not re-save in 5.0.
- Tested and working: all 583 meshes extract metadata correctly. 8 test renders produce correct isolated transparent PNGs with tissue-type colors.

### Metadata already extracted
Saved at `~/anibodymouse/claude_mouse/supplementary/mesh_catalog.json` and `.csv`:
- 583 meshes, 16.7M evaluated verts, 6081.7 mm³ total volume
- Largest: CNS (520.9 mm³), Retopo_161.005 muscle (263.9 mm³), kidneys (~190 mm³), Skull (196.1 mm³)

### Test renders verified working
8 meshes rendered as isolated transparent PNGs with tissue-type coloring at `~/anibodymouse/claude_mouse/supplementary/renders/`:
humerus_right (bone), Skull (bone), Pectoralis_major_superficial_right (muscle), Gluteus medius (muscle), heart (cardiac), CNS (central nervous system), Femur_right (bone), Retopo_3.068 (tendon)

---

## WHAT TO WORK ON NEXT

Priority order for the paper deadline:

1. **Full 583-mesh render run** — Run batch_render.py with --mode all. Then assemble into supplementary contact sheet figures grouped by tissue type and body region.

2. **Naming/validation tools** — Many meshes are named "Retopo_X.XXX" (retopologized from scan data). Need operators to: list all unnamed meshes, suggest anatomical names, bulk rename, validate naming conventions.

3. **Symmetrization tools** — Muscles are only on the right side. Need operators to mirror right-side muscles to left, following the bone symmetry that's already done.

4. **Figure generation scripts** — Assemble renders into publication figures. Whole-body views (Fig 3), exploded anatomy (Fig 2), forelimb detail views.

5. **MuJoCo export preparation** — Validate the model is ready for dm_control export. Check joint definitions, DOF count, muscle attachment sites.

6. **Paper writing assistance** — Methods section drafts, supplementary table formatting, figure caption drafts.

---

## HOW TO ACCESS THE BLENDER MODEL

The .blend file is at: `~/anibodymouse/claude_mouse/claude_mouse.blend`

To run scripts against it:
```bash
/Applications/Blender.app/Contents/MacOS/Blender --background ~/anibodymouse/claude_mouse/claude_mouse.blend --python scripts/batch_render.py
```

Blender 5.0.1 is installed at: `/Applications/Blender.app/Contents/MacOS/Blender`

For quick Blender Python queries:
```bash
blender --background model.blend --python-expr "import bpy; print(len(bpy.data.objects))"
```
