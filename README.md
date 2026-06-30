# Blender Advanced Timeline/Dropsheet

## Overview
Managing complex animations in Blender often becomes a cumbersome process when dealing with hundreds of scattered keyframes 
across objects, materials, and Geometry Nodes. While the NLA editor handles broad actions, it lacks the ability to visually 
group disparate data blocks into a single, easily manageable sequence. 

This solves this by introducing a familiar video-editing-like sequence container directly into Blender's Dopesheet. It allows animators to wrap complex blocks of keyframes into a unified, visual clip. Instead of micro-managing individual keys, users can grab, slide, trim, and snap entire multi-object animation blocks as a single, cohesive unit.

---

## Log

### 03.06
* **Dynamic OpenGL Drawing:** Injects a custom visual layer into the Dopesheet using `POST_PIXEL` space.
* **Customizable:** Clip names and custom colors can be adjusted.
* **Click-and-Drag Editing:** Click the body to move the entire sequence, or grab the edges to trim/extend the clip boundaries.
* **Native Blender Keymap Integration:** 'G' to Grab, Live Snapping, Escape / Cancel
* **Dedicated Sidebar UI (N-Panel)**
---

## Usage

1. Open the **Dopesheet** editor in Blender.
2. Click **Start Clip Tool** in the top header menu.
3. **Select:** Click the clip to select it (borders turn yellow).
4. **Move:** Click and drag the center body, or press `G`.
5. **Resize:** Click and drag the darker left/right edge handles.
6. **Snap:** Press `Shift + S` to snap the clip to the current frame.
7. **Properties:** Press `N` to open the sidebar and navigate to the **Clip Tool** tab to change the name, color, and height depth.

## Ideas:
1. Nesting
2. Group linking
3. Responsive keyframes to the group(%, constant, etc...)