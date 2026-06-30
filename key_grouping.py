import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import blf
import math


# --- 1. DATA STRUCTURES ---
class AnimKeyReference(bpy.types.PropertyGroup):
    action_name: bpy.props.StringProperty()
    data_path: bpy.props.StringProperty()
    array_index: bpy.props.IntProperty()
    kf_index: bpy.props.IntProperty()
    orig_frame: bpy.props.FloatProperty()


class AnimGroup(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Group Name", default="New Group")
    start: bpy.props.FloatProperty(name="Start")
    end: bpy.props.FloatProperty(name="End")

    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', default=(0.2, 0.6, 1.0, 0.3), size=4, min=0.0, max=1.0
    )
    vertical_depth: bpy.props.IntProperty(name="Vertical Depth", default=1, min=1)
    keys: bpy.props.CollectionProperty(type=AnimKeyReference)

    responsive_mode: bpy.props.EnumProperty(
        name="Behavior",
        items=[('PROPORTIONAL', "Proportional (%)", ""), ('CONSTANT', "Constant", "")],
        default='CONSTANT'
    )

    is_selected: bpy.props.BoolProperty(default=False)
    active_part: bpy.props.StringProperty(default='NONE')


clip_interaction = {
    "drag_mode": 'NONE',
    "drag_offset": 0.0,
    "orig_start": 0.0,
    "orig_end": 0.0,
    "active_group_idx": -1
}

addon_keymaps = []


def get_fcu_map(action):
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, "channelbags"):
                    for cb in strip.channelbags:
                        fcurves.extend(cb.fcurves)
    elif hasattr(action, "fcurves"):
        fcurves = action.fcurves
    return {fcu.data_path + str(fcu.array_index): fcu for fcu in fcurves}


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
    if region.type != 'WINDOW': return

    for clip in context.scene.anim_groups:
        start_px_coord = region.view2d.view_to_region(clip.start, 0, clip=False)
        end_px_coord = region.view2d.view_to_region(clip.end, 0, clip=False)
        if not start_px_coord or not end_px_coord: continue

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

        if box_width < 1 or box_height < 1: continue

        base_color = list(clip.color)
        handle_color = list(base_color)
        handle_color[3] = min(1.0, base_color[3] + 0.3)

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

        arr_lx = x1 + (handle_width / 2)
        verts_l = ((arr_lx + 4, cy + 6), (arr_lx + 4, cy - 6), (arr_lx - 4, cy))
        inds_tri = ((0, 1, 2),)
        batch_l = batch_for_shader(shader, 'TRIS', {"pos": verts_l}, indices=inds_tri)
        shader.uniform_float("color", color_l)
        batch_l.draw(shader)

        arr_rx = x2 - (handle_width / 2)
        verts_r = ((arr_rx - 4, cy + 6), (arr_rx - 4, cy - 6), (arr_rx + 4, cy))
        batch_r = batch_for_shader(shader, 'TRIS', {"pos": verts_r}, indices=inds_tri)
        shader.uniform_float("color", color_r)
        batch_r.draw(shader)

        gpu.state.blend_set('NONE')

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


# --- 3. OPERATORS ---
class ANIM_OT_create_clip_group(bpy.types.Operator):
    bl_idname = "anim.create_clip_group"
    bl_label = "Group Selected Keys"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_keys_data = []
        unique_fcurves = set()
        selected_key_ids = set()
        min_frame = float('inf')
        max_frame = float('-inf')

        for action in bpy.data.actions:
            fcu_map = get_fcu_map(action)
            for fcu_id, fcu in fcu_map.items():
                for i, kf in enumerate(fcu.keyframe_points):
                    if kf.select_control_point:
                        co_x = kf.co[0]
                        min_frame = min(min_frame, co_x)
                        max_frame = max(max_frame, co_x)
                        unique_fcurves.add(f"{action.name}_{fcu_id}")
                        selected_keys_data.append({
                            'action': action.name,
                            'path': fcu.data_path,
                            'array_idx': fcu.array_index,
                            'kf_idx': i,
                            'frame': co_x
                        })
                        selected_key_ids.add(f"{action.name}_{fcu_id}_{i}")

        if not selected_keys_data:
            self.report({'WARNING'}, "No selected keyframes found.")
            return {'CANCELLED'}

        groups_to_delete = []
        for i, group in enumerate(context.scene.anim_groups):
            for k_ref in group.keys:
                k_id = f"{k_ref.action_name}_{k_ref.data_path}{k_ref.array_index}_{k_ref.kf_index}"
                if k_id in selected_key_ids:
                    groups_to_delete.append(i)
                    break

        for i in reversed(groups_to_delete):
            context.scene.anim_groups.remove(i)

        if min_frame == max_frame:
            max_frame = min_frame + 1.0

        new_group = context.scene.anim_groups.add()
        new_group.name = f"Group {len(context.scene.anim_groups)}"
        new_group.start = min_frame
        new_group.end = max_frame
        new_group.vertical_depth = len(unique_fcurves)

        for k_data in selected_keys_data:
            k_ref = new_group.keys.add()
            k_ref.action_name = k_data['action']
            k_ref.data_path = k_data['path']
            k_ref.array_index = k_data['array_idx']
            k_ref.kf_index = k_data['kf_idx']
            k_ref.orig_frame = k_data['frame']

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class ANIM_OT_delete_clip_group(bpy.types.Operator):
    bl_idname = "anim.delete_clip_group"
    bl_label = "Delete Group"
    bl_options = {'REGISTER', 'UNDO'}

    delete_keys: bpy.props.BoolProperty(default=False)
    group_idx: bpy.props.IntProperty()

    def execute(self, context):
        if self.group_idx < 0 or self.group_idx >= len(context.scene.anim_groups):
            return {'CANCELLED'}

        group = context.scene.anim_groups[self.group_idx]

        if self.delete_keys:
            fcu_maps = {}
            keys_to_delete = {}

            for k_ref in group.keys:
                action = bpy.data.actions.get(k_ref.action_name)
                if not action: continue

                if action.name not in fcu_maps:
                    fcu_maps[action.name] = get_fcu_map(action)

                fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
                if fcu:
                    fcu_key = (action.name, fcu.data_path, fcu.array_index)
                    if fcu_key not in keys_to_delete:
                        keys_to_delete[fcu_key] = {'fcu': fcu, 'indices': []}
                    keys_to_delete[fcu_key]['indices'].append(k_ref.kf_index)

            for data in keys_to_delete.values():
                fcu = data['fcu']
                indices = data['indices']
                indices.sort(reverse=True)
                for idx in indices:
                    if idx < len(fcu.keyframe_points):
                        fcu.keyframe_points.remove(fcu.keyframe_points[idx])

        context.scene.anim_groups.remove(self.group_idx)

        if clip_interaction.get("active_group_idx") == self.group_idx:
            clip_interaction["active_group_idx"] = -1

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}


class ANIM_OT_interactive_nest_tool(bpy.types.Operator):
    bl_idname = "anim.interactive_nest_tool"
    bl_label = "Interactive Clip Tool"
    bl_options = {'UNDO'}

    def deselect_all_keyframes(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'DOPESHEET_EDITOR':
                    with context.temp_override(window=window, area=area):
                        bpy.ops.action.select_all(action='DESELECT')
                    return

    def capture_keys(self, group):
        fcu_maps = {}
        for k_ref in group.keys:
            action = bpy.data.actions.get(k_ref.action_name)
            if not action: continue
            if action.name not in fcu_maps:
                fcu_maps[action.name] = get_fcu_map(action)

            fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
            if fcu and k_ref.kf_index < len(fcu.keyframe_points):
                k_ref.orig_frame = fcu.keyframe_points[k_ref.kf_index].co[0]

    def update_keys(self, group, orig_start, orig_end):
        orig_length = orig_end - orig_start
        if orig_length <= 0: orig_length = 1.0
        new_length = group.end - group.start
        fcu_maps = {}

        for k_ref in group.keys:
            action = bpy.data.actions.get(k_ref.action_name)
            if not action: continue
            if action.name not in fcu_maps:
                fcu_maps[action.name] = get_fcu_map(action)

            fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
            if not fcu or k_ref.kf_index >= len(fcu.keyframe_points): continue

            kf = fcu.keyframe_points[k_ref.kf_index]
            old_frame = kf.co[0]

            if group.responsive_mode == 'PROPORTIONAL':
                t = (k_ref.orig_frame - orig_start) / orig_length
                new_frame = group.start + (t * new_length)
            else:
                new_frame = k_ref.orig_frame + (group.start - orig_start)

            delta = new_frame - old_frame
            kf.co[0] = new_frame
            kf.handle_left[0] += delta
            kf.handle_right[0] += delta

    def invoke(self, context, event):
        if context.area.type != 'DOPESHEET_EDITOR':
            return {'PASS_THROUGH'}

        window_region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not window_region:
            return {'PASS_THROUGH'}

        # Ensure the click strictly occurred inside the core timeline bounds (not the N-Panel)
        mx = event.mouse_x - window_region.x
        my = event.mouse_y - window_region.y

        if not (0 <= mx <= window_region.width and 0 <= my <= window_region.height):
            return {'PASS_THROUGH'}

        view2d = window_region.view2d
        frame, _ = view2d.region_to_view(mx, my)

        hit_detected = False
        clip_interaction["active_group_idx"] = -1

        for idx, group in enumerate(context.scene.anim_groups):
            start_px_coord = view2d.view_to_region(group.start, 0, clip=False)
            end_px_coord = view2d.view_to_region(group.end, 0, clip=False)
            if not start_px_coord or not end_px_coord:
                continue

            x1, _ = start_px_coord
            x2, _ = end_px_coord
            y2 = window_region.height - 50
            y1 = y2 - (group.vertical_depth * 34)

            if y1 <= my <= y2 and (x1 - 15) <= mx <= (x2 + 15):
                hit_detected = True
                clip_interaction["active_group_idx"] = idx
                clip_interaction["orig_start"] = group.start
                clip_interaction["orig_end"] = group.end

                for g in context.scene.anim_groups:
                    g.is_selected = False
                group.is_selected = True

                self.capture_keys(group)

                if abs(mx - x1) < 15:
                    group.active_part = 'LEFT'
                    clip_interaction["drag_mode"] = 'LEFT'
                    clip_interaction["drag_offset"] = frame - group.start
                elif abs(mx - x2) < 15:
                    group.active_part = 'RIGHT'
                    clip_interaction["drag_mode"] = 'RIGHT'
                    clip_interaction["drag_offset"] = frame - group.end
                else:
                    group.active_part = 'BODY'
                    clip_interaction["drag_mode"] = 'BODY'
                    clip_interaction["drag_offset"] = frame - group.start

                self.deselect_all_keyframes(context)
                break

        if hit_detected:
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        else:
            # Drop selection only if an empty space inside the window was clicked.
            deselected = False
            for g in context.scene.anim_groups:
                if g.is_selected:
                    g.is_selected = False
                    deselected = True
            if deselected:
                context.area.tag_redraw()
            return {'PASS_THROUGH'}

    def modal(self, context, event):
        if not context.area or context.area.type != 'DOPESHEET_EDITOR': return {'CANCELLED'}
        window_region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not window_region: return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            clip_interaction["drag_mode"] = 'NONE'
            if clip_interaction["active_group_idx"] >= 0:
                group = context.scene.anim_groups[clip_interaction["active_group_idx"]]
                group.active_part = 'NONE'
            context.area.tag_redraw()
            return {'FINISHED'}

        elif event.type == 'MOUSEMOVE':
            if clip_interaction["drag_mode"] != 'NONE' and clip_interaction["active_group_idx"] >= 0:
                view2d = window_region.view2d
                mx = event.mouse_x - window_region.x
                my = event.mouse_y - window_region.y
                frame, _ = view2d.region_to_view(mx, my)

                group = context.scene.anim_groups[clip_interaction["active_group_idx"]]
                target_frame = round(frame - clip_interaction["drag_offset"])
                orig_start = clip_interaction["orig_start"]

                if group.responsive_mode == 'CONSTANT':
                    orig_length = clip_interaction["orig_end"] - orig_start
                    keys_max_offset = max((k.orig_frame - orig_start for k in group.keys), default=orig_length)

                    if clip_interaction["drag_mode"] == 'RIGHT':
                        min_end = group.start + keys_max_offset
                        if target_frame < min_end: target_frame = min_end
                    elif clip_interaction["drag_mode"] == 'LEFT':
                        max_start = group.end - keys_max_offset
                        if target_frame > max_start: target_frame = max_start

                if clip_interaction["drag_mode"] == 'BODY':
                    length = group.end - group.start
                    group.start = target_frame
                    group.end = target_frame + length
                elif clip_interaction["drag_mode"] == 'LEFT':
                    if target_frame <= group.end - 1: group.start = target_frame
                elif clip_interaction["drag_mode"] == 'RIGHT':
                    if target_frame >= group.start + 1: group.end = target_frame

                self.update_keys(group, orig_start, clip_interaction["orig_end"])
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}


# --- 4. UI PANELS & MENUS ---
class DOPESHEET_PT_clip_info(bpy.types.Panel):
    bl_label = "Group Information"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Clip Tool"

    def draw(self, context):
        layout = self.layout
        active_group = None
        active_group_idx = -1

        for i, group in enumerate(context.scene.anim_groups):
            if group.is_selected:
                active_group = group
                active_group_idx = i
                break

        if not active_group:
            layout.label(text="No group selected.")
            layout.label(text="Click a group to view properties.", icon='INFO')
            return

        col = layout.column(align=True)
        col.prop(active_group, "name")
        col.prop(active_group, "color")
        col.prop(active_group, "responsive_mode")

        layout.separator()
        col2 = layout.column(align=True)
        col2.prop(active_group, "vertical_depth", text="Track Depth")

        layout.separator()
        layout.label(text=f"Bounds: Frame {round(active_group.start)} to {round(active_group.end)}")

        layout.separator()

        box = layout.box()
        box.label(text="Danger Zone", icon='ERROR')
        row = box.row(align=True)

        op_del_group = row.operator("anim.delete_clip_group", text="Remove Group Only")
        op_del_group.delete_keys = False
        op_del_group.group_idx = active_group_idx

        op_del_keys = row.operator("anim.delete_clip_group", text="Delete Group + Keys")
        op_del_keys.delete_keys = True
        op_del_keys.group_idx = active_group_idx


def draw_dopesheet_context_menu(self, context):
    self.layout.separator()
    self.layout.operator("anim.create_clip_group", icon='GROUP')


# --- 5. REGISTRATION ---
classes = (
    AnimKeyReference,
    AnimGroup,
    ANIM_OT_create_clip_group,
    ANIM_OT_delete_clip_group,
    ANIM_OT_interactive_nest_tool,
    DOPESHEET_PT_clip_info,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.anim_groups = bpy.props.CollectionProperty(type=AnimGroup)
    bpy.types.DOPESHEET_MT_context_menu.append(draw_dopesheet_context_menu)

    if "anim_clip_handler" not in bpy.app.driver_namespace:
        bpy.app.driver_namespace["anim_clip_handler"] = bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            draw_clip_overlays, (), 'WINDOW', 'POST_PIXEL'
        )

    wm = bpy.context.window_manager
    if wm and wm.keyconfigs and wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        kmi = km.keymap_items.new("anim.interactive_nest_tool", 'LEFTMOUSE', 'PRESS')
        addon_keymaps.append((km, kmi))


def unregister():
    wm = bpy.context.window_manager
    if wm and wm.keyconfigs and wm.keyconfigs.addon:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    if hasattr(bpy.types.DOPESHEET_MT_context_menu, "draw") and hasattr(bpy.types.DOPESHEET_MT_context_menu.draw,
                                                                        "_draw_funcs"):
        funcs = [f for f in bpy.types.DOPESHEET_MT_context_menu.draw._draw_funcs if
                 f.__name__ == 'draw_dopesheet_context_menu']
        for f in funcs:
            try:
                bpy.types.DOPESHEET_MT_context_menu.remove(f)
            except ValueError:
                pass

    if "anim_clip_handler" in bpy.app.driver_namespace:
        try:
            bpy.types.SpaceDopeSheetEditor.draw_handler_remove(bpy.app.driver_namespace["anim_clip_handler"], 'WINDOW')
        except ValueError:
            pass
        del bpy.app.driver_namespace["anim_clip_handler"]

    if hasattr(bpy.types.Scene, "anim_groups"):
        del bpy.types.Scene.anim_groups

    for cls in reversed(classes):
        registered_cls = getattr(bpy.types, cls.__name__, None)
        if registered_cls:
            try:
                bpy.utils.unregister_class(registered_cls)
            except RuntimeError:
                pass


if __name__ == "__main__":
    unregister()
    register()