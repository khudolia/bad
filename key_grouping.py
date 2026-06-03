import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import blf
import math


# --- 1. DATA STRUCTURES ---
class ActiveClipProps(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Clip Name", default="Main Action Sequence")
    start: bpy.props.FloatProperty(name="Start", default=24.0)
    end: bpy.props.FloatProperty(name="End", default=96.0)
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', default=(0.2, 0.6, 1.0, 0.3), size=4, min=0.0, max=1.0
    )
    is_selected: bpy.props.BoolProperty(name="Selected", default=False)
    active_part: bpy.props.StringProperty(name="Active Part", default='NONE')
    vertical_depth: bpy.props.IntProperty(name="Vertical Depth", default=1, min=1, max=50)


clip_interaction = {
    "drag_mode": 'NONE',
    "drag_offset": 0.0,
    "is_g_mode": False,
    "orig_start": 0.0,
    "orig_end": 0.0
}


# --- 2. DRAWING FUNCTIONS ---
def get_shader(mode='UNIFORM_COLOR'):
    try:
        return gpu.shader.from_builtin(mode)
    except ValueError:
        return gpu.shader.from_builtin('2D_UNIFORM_COLOR')


def draw_rounded_rect(x, y, width, height, radius, color):
    shader = get_shader()
    segments = 8
    verts = []

    for i in range(segments + 1):
        angle = math.pi + (math.pi / 2) * (i / segments)
        verts.append((x + radius + math.cos(angle) * radius, y + radius + math.sin(angle) * radius))
    for i in range(segments + 1):
        angle = math.pi * 1.5 + (math.pi / 2) * (i / segments)
        verts.append((x + width - radius + math.cos(angle) * radius, y + radius + math.sin(angle) * radius))
    for i in range(segments + 1):
        angle = 0 + (math.pi / 2) * (i / segments)
        verts.append((x + width - radius + math.cos(angle) * radius, y + height - radius + math.sin(angle) * radius))
    for i in range(segments + 1):
        angle = math.pi / 2 + (math.pi / 2) * (i / segments)
        verts.append((x + radius + math.cos(angle) * radius, y + height - radius + math.sin(angle) * radius))

    center_x = x + width / 2
    center_y = y + height / 2
    fan_verts = [(center_x, center_y)] + verts + [verts[0]]
    inds = [(0, i, i + 1) for i in range(1, len(fan_verts) - 1)]

    batch = batch_for_shader(shader, 'TRIS', {"pos": fan_verts}, indices=inds)
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')


def draw_clip_overlays():
    context = bpy.context
    region = context.region
    clip = context.scene.anim_clip_tool
    if region.type != 'WINDOW': return

    start_px_coord = region.view2d.view_to_region(clip.start, 0, clip=False)
    end_px_coord = region.view2d.view_to_region(clip.end, 0, clip=False)
    if not start_px_coord or not end_px_coord: return

    x1, _ = start_px_coord
    x2, _ = end_px_coord

    track_height = 32
    total_drop_pixels = clip.vertical_depth * (track_height + 2)
    y2 = region.height - 50
    y1 = y2 - total_drop_pixels

    box_width = x2 - x1
    box_height = y2 - y1
    cy = y1 + (box_height / 2)
    handle_width = min(20, box_width * 0.15)
    if box_width < 1 or box_height < 1: return

    base_color = list(clip.color)
    if clip.is_selected:
        base_color[3] = min(1.0, base_color[3] + 0.15)

    handle_color = list(base_color)
    handle_color[3] = min(1.0, base_color[3] + 0.3)

    # DRAW RECTS
    draw_rounded_rect(x1, y1, handle_width, box_height, radius=6, color=handle_color)
    draw_rounded_rect(x1 + handle_width - 2, y1, box_width - (handle_width * 2) + 4, box_height, radius=0,
                      color=base_color)
    draw_rounded_rect(x2 - handle_width, y1, handle_width, box_height, radius=6, color=handle_color)

    shader = get_shader()
    gpu.state.blend_set('ALPHA')
    shader.bind()

    if clip.is_selected:
        out_color = (1.0, 0.8, 0.0, 0.8) if clip.active_part == 'BODY' else (1.0, 1.0, 1.0, 0.8)
        verts = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
        inds = ((0, 1), (1, 2), (2, 3), (3, 0))
        batch = batch_for_shader(shader, 'LINES', {"pos": verts}, indices=inds)
        shader.uniform_float("color", out_color)
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

    c_unsel = (1.0, 1.0, 1.0, 0.9)
    c_sel = (1.0, 0.8, 0.0, 1.0)
    color_l = c_sel if (clip.is_selected and clip.active_part == 'LEFT') else c_unsel
    color_r = c_sel if (clip.is_selected and clip.active_part == 'RIGHT') else c_unsel

    # Left Arrow (<|)
    arr_lx = x1 + (handle_width / 2)
    verts_l = ((arr_lx + 4, cy + 6), (arr_lx + 4, cy - 6), (arr_lx - 4, cy))
    inds_tri = ((0, 1, 2),)
    batch_l = batch_for_shader(shader, 'TRIS', {"pos": verts_l}, indices=inds_tri)
    shader.uniform_float("color", color_l)
    batch_l.draw(shader)

    # Right Arrow (|>)
    arr_rx = x2 - (handle_width / 2)
    verts_r = ((arr_rx - 4, cy + 6), (arr_rx - 4, cy - 6), (arr_rx + 4, cy))
    batch_r = batch_for_shader(shader, 'TRIS', {"pos": verts_r}, indices=inds_tri)
    shader.uniform_float("color", color_r)
    batch_r.draw(shader)

    gpu.state.blend_set('NONE')

    # DRAW TEXT
    font_id = 0
    blf.size(font_id, 16)
    text_width = blf.dimensions(font_id, clip.name)[0]
    text_x = x1 + ((x2 - x1) / 2.0) - (text_width / 2.0)
    text_y = y2 - 20

    blf.position(font_id, text_x, text_y, 0)
    blf.enable(font_id, blf.SHADOW)
    blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 0.8)
    blf.shadow_offset(font_id, 1, -1)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    blf.draw(font_id, clip.name)
    blf.disable(font_id, blf.SHADOW)


# --- 3. CUSTOM SHIFT+S SNAP MENU & OPERATOR ---
class ANIM_OT_clip_snap(bpy.types.Operator):
    bl_idname = "anim.clip_snap"
    bl_label = "Snap Clip"
    snap_type: bpy.props.StringProperty()

    def execute(self, context):
        clip = context.scene.anim_clip_tool
        target_frame = context.scene.frame_current

        if self.snap_type == 'CFRA':
            if clip.active_part == 'BODY':
                length = clip.end - clip.start
                clip.start = target_frame
                clip.end = target_frame + length
            elif clip.active_part == 'LEFT':
                if target_frame <= clip.end - 1: clip.start = target_frame
            elif clip.active_part == 'RIGHT':
                if target_frame >= clip.start + 1: clip.end = target_frame

        context.area.tag_redraw()
        return {'FINISHED'}


class ANIM_MT_clip_snap(bpy.types.Menu):
    bl_label = "Snap Clip"
    bl_idname = "ANIM_MT_clip_snap"

    def draw(self, context):
        layout = self.layout
        layout.operator("anim.clip_snap", text="Selection to Current Frame").snap_type = 'CFRA'


# --- 4. THE INTERACTIVE LOGIC ---
class ANIM_OT_interactive_nest_tool(bpy.types.Operator):
    bl_idname = "anim.interactive_nest_tool"
    bl_label = "Interactive Clip Tool"

    def deselect_all_keyframes(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'DOPESHEET_EDITOR':
                    with context.temp_override(window=window, area=area):
                        bpy.ops.action.select_all(action='DESELECT')
                    return

    def modal(self, context, event):
        if not context.area or context.area.type != 'DOPESHEET_EDITOR': return {'PASS_THROUGH'}

        clip = context.scene.anim_clip_tool
        window_region = None
        for r in context.area.regions:
            if r.type == 'WINDOW':
                window_region = r
                break
        if not window_region: return {'PASS_THROUGH'}

        view2d = window_region.view2d
        mx = event.mouse_x - window_region.x
        my = event.mouse_y - window_region.y
        frame, _ = view2d.region_to_view(mx, my)

        start_px_coord = view2d.view_to_region(clip.start, 0, clip=False)
        end_px_coord = view2d.view_to_region(clip.end, 0, clip=False)
        if not start_px_coord or not end_px_coord: return {'PASS_THROUGH'}

        x_start_px = start_px_coord[0]
        x_end_px = end_px_coord[0]

        track_height = 32
        total_drop_pixels = clip.vertical_depth * (track_height + 2)
        y2 = window_region.height - 50
        y1 = y2 - total_drop_pixels

        # 1. HANDLE CLICKS
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if mx < 0 or mx > window_region.width or my < 0 or my > window_region.height:
                    return {'PASS_THROUGH'}

                if clip_interaction["is_g_mode"]:
                    clip_interaction["drag_mode"] = 'NONE'
                    clip_interaction["is_g_mode"] = False
                    return {'RUNNING_MODAL'}

                clip_interaction["orig_start"] = clip.start
                clip_interaction["orig_end"] = clip.end

                if abs(mx - x_start_px) < 15 and y1 <= my <= y2:
                    clip.active_part = 'LEFT'
                    clip_interaction["drag_mode"] = 'LEFT'
                    clip_interaction["drag_offset"] = frame - clip.start
                    clip.is_selected = True
                    self.deselect_all_keyframes(context)
                    return {'RUNNING_MODAL'}

                elif abs(mx - x_end_px) < 15 and y1 <= my <= y2:
                    clip.active_part = 'RIGHT'
                    clip_interaction["drag_mode"] = 'RIGHT'
                    clip_interaction["drag_offset"] = frame - clip.end
                    clip.is_selected = True
                    self.deselect_all_keyframes(context)
                    return {'RUNNING_MODAL'}

                elif clip.start <= frame <= clip.end and y1 <= my <= y2:
                    clip.active_part = 'BODY'
                    clip_interaction["drag_mode"] = 'BODY'
                    clip_interaction["drag_offset"] = frame - clip.start
                    clip.is_selected = True
                    self.deselect_all_keyframes(context)
                    return {'RUNNING_MODAL'}

                else:
                    clip.is_selected = False
                    clip.active_part = 'NONE'
                    context.area.tag_redraw()
                    return {'PASS_THROUGH'}

            elif event.value == 'RELEASE':
                if clip_interaction["drag_mode"] != 'NONE' and not clip_interaction["is_g_mode"]:
                    clip_interaction["drag_mode"] = 'NONE'
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}

        # 2. HANDLE 'G' KEY
        elif event.type == 'G' and event.value == 'PRESS':
            if clip.is_selected and clip_interaction["drag_mode"] == 'NONE':
                clip_interaction["orig_start"] = clip.start
                clip_interaction["orig_end"] = clip.end
                clip_interaction["is_g_mode"] = True

                part = clip.active_part if clip.active_part != 'NONE' else 'BODY'
                clip_interaction["drag_mode"] = part

                if part == 'LEFT':
                    clip_interaction["drag_offset"] = frame - clip.start
                elif part == 'RIGHT':
                    clip_interaction["drag_offset"] = frame - clip.end
                else:
                    clip_interaction["drag_offset"] = frame - clip.start

                return {'RUNNING_MODAL'}

        # 3. CUSTOM SHIFT+S MENU
        elif event.type == 'S' and event.shift and event.value == 'PRESS':
            if clip.is_selected and clip.active_part != 'NONE':
                bpy.ops.wm.call_menu('INVOKE_DEFAULT', name="ANIM_MT_clip_snap")
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}

        # 4. CANCEL / REVERT
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            if clip_interaction["drag_mode"] != 'NONE':
                clip.start = clip_interaction["orig_start"]
                clip.end = clip_interaction["orig_end"]
                clip_interaction["drag_mode"] = 'NONE'
                clip_interaction["is_g_mode"] = False
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

        # 5. MOUSE MOVEMENT
        elif event.type == 'MOUSEMOVE' and clip_interaction["drag_mode"] != 'NONE':
            target_frame = round(frame - clip_interaction["drag_offset"])

            if clip_interaction["drag_mode"] == 'BODY':
                length = clip.end - clip.start
                clip.start = target_frame
                clip.end = target_frame + length
            elif clip_interaction["drag_mode"] == 'LEFT':
                if target_frame <= clip.end - 1: clip.start = target_frame
            elif clip_interaction["drag_mode"] == 'RIGHT':
                if target_frame >= clip.start + 1: clip.end = target_frame

            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.area.type != 'DOPESHEET_EDITOR': return {'CANCELLED'}

        # Save Draw Handler explicitly to persistent memory so we can delete it later
        if "anim_clip_handler" not in bpy.app.driver_namespace:
            bpy.app.driver_namespace["anim_clip_handler"] = bpy.types.SpaceDopeSheetEditor.draw_handler_add(
                draw_clip_overlays, (), 'WINDOW', 'POST_PIXEL'
            )

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


# --- 5. THE N-PANEL MENU (Sidebar UI) ---
class DOPESHEET_PT_clip_info(bpy.types.Panel):
    bl_label = "Clip Information"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Clip Tool"

    def draw(self, context):
        layout = self.layout
        clip = context.scene.anim_clip_tool

        if not clip.is_selected:
            layout.label(text="No clip selected.")
            layout.label(text="Click a clip to view properties.", icon='INFO')
            return

        col = layout.column(align=True)
        col.prop(clip, "name")
        col.prop(clip, "color")

        layout.separator()
        col2 = layout.column(align=True)
        col2.prop(clip, "vertical_depth", text="Track Depth")

        layout.separator()
        layout.label(text=f"Bounds: Frame {round(clip.start)} to {round(clip.end)}")
        layout.separator()

        box = layout.box()
        box.label(text="Keys Contained:", icon='KEY_HLT')
        box.label(text="• Cube.location")
        box.label(text="• ShaderNodeTree.BaseColor")


classes = (
    ActiveClipProps,
    ANIM_OT_clip_snap,
    ANIM_MT_clip_snap,
    ANIM_OT_interactive_nest_tool,
    DOPESHEET_PT_clip_info,
)


def draw_header_button(self, context):
    self.layout.separator()
    self.layout.operator("anim.interactive_nest_tool", text="Start Clip Tool", icon='UV_SYNC_SELECT')


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.anim_clip_tool = bpy.props.PointerProperty(type=ActiveClipProps)
    bpy.types.DOPESHEET_HT_header.append(draw_header_button)


def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass

    try:
        del bpy.types.Scene.anim_clip_tool
    except AttributeError:
        pass

    # Aggressively hunt down and remove ghost UI Buttons from older runs
    if hasattr(bpy.types.DOPESHEET_HT_header, "draw") and hasattr(bpy.types.DOPESHEET_HT_header.draw, "_draw_funcs"):
        for f in list(bpy.types.DOPESHEET_HT_header.draw._draw_funcs):
            if f.__name__ == 'draw_header_button':
                try:
                    bpy.types.DOPESHEET_HT_header.remove(f)
                except Exception:
                    pass

    # Aggressively hunt down and remove ghost Draw Handlers from older runs
    if "anim_clip_handler" in bpy.app.driver_namespace:
        try:
            bpy.types.SpaceDopeSheetEditor.draw_handler_remove(bpy.app.driver_namespace["anim_clip_handler"], 'WINDOW')
        except Exception:
            pass
        del bpy.app.driver_namespace["anim_clip_handler"]


if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()
    print("Interactive Clip Tool Loaded Successfully!")