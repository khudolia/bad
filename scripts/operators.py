import bpy
import colorsys
from .state import clip_interaction

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


def sync_object_selection(context, group):
    # 1. Clear current viewport selection
    for obj in context.scene.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass  # Ignore objects that cannot be deselected due to current mode

    if not group:
        return

    # 2. Extract unique action names from the group
    action_names = {k_ref.action_name for k_ref in group.keys}

    # 3. Select relevant objects
    for obj in context.scene.objects:
        if obj.animation_data and obj.animation_data.action:
            if obj.animation_data.action.name in action_names:
                # Ensure the object is visible and selectable to prevent context crashes
                if not obj.hide_get() and not obj.hide_viewport:
                    try:
                        obj.select_set(True)
                        context.view_layer.objects.active = obj
                    except RuntimeError:
                        pass

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

        group_count = len(context.scene.anim_groups)
        hue = (group_count * 0.618033988749895) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.6, 0.9)  # 0.6 saturation, 0.9 value ensures bright, visible pastels
        new_group.color = (r, g, b, 0.3)

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

                # --- NEW: Trigger Viewport Selection Sync ---
                sync_object_selection(context, group)

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
            deselected = False
            for g in context.scene.anim_groups:
                if g.is_selected:
                    g.is_selected = False
                    deselected = True
            if deselected:
                sync_object_selection(context, None)
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

class ANIM_OT_select_group_from_viewport(bpy.types.Operator):
    bl_idname = "anim.select_group_from_viewport"
    bl_label = "Select Anim Group"
    bl_options = {'REGISTER', 'UNDO'}

    group_idx: bpy.props.IntProperty()

    def execute(self, context):
        if self.group_idx < 0 or self.group_idx >= len(context.scene.anim_groups):
            return {'CANCELLED'}

        group = context.scene.anim_groups[self.group_idx]

        # 1. Update UI Selection State
        for g in context.scene.anim_groups:
            g.is_selected = False
        group.is_selected = True

        # 2. Map Action Names to Scene Objects
        action_names = {k_ref.action_name for k_ref in group.keys}

        bpy.ops.object.select_all(action='DESELECT')
        for obj in context.scene.objects:
            if obj.animation_data and obj.animation_data.action:
                if obj.animation_data.action.name in action_names:
                    obj.select_set(True)
                    context.view_layer.objects.active = obj

        # 3. Move Playhead to Group Start
        context.scene.frame_current = int(group.start)

        # 4. Context Override: Force Dopesheet to center on playhead
        dopesheet_area = next((a for a in context.screen.areas if a.type == 'DOPESHEET_EDITOR'), None)
        if dopesheet_area:
            dopesheet_region = next((r for r in dopesheet_area.regions if r.type == 'WINDOW'), None)
            if dopesheet_region:
                with context.temp_override(area=dopesheet_area, region=dopesheet_region):
                    try:
                        bpy.ops.action.view_frame()
                    except RuntimeError:
                        pass  # Fails silently if view_frame cannot execute

        # 5. Force UI Refresh
        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}

class ANIM_OT_select_single_object(bpy.types.Operator):
    bl_idname = "anim.select_single_object"
    bl_label = "Select Object"
    bl_options = {'UNDO'}

    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        if not obj:
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')

        if not obj.hide_get() and not obj.hide_viewport:
            obj.select_set(True)
            context.view_layer.objects.active = obj

        return {'FINISHED'}


class ANIM_OT_remove_object_from_group(bpy.types.Operator):
    bl_idname = "anim.remove_object_from_group"
    bl_label = "Remove Object"
    bl_options = {'UNDO'}

    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        active_group = next((g for g in context.scene.anim_groups if g.is_selected), None)

        if not obj or not active_group:
            return {'CANCELLED'}

        if not obj.animation_data or not obj.animation_data.action:
            return {'CANCELLED'}

        action_name = obj.animation_data.action.name

        # Iterate backwards to safely remove items from the collection
        for i in range(len(active_group.keys) - 1, -1, -1):
            if active_group.keys[i].action_name == action_name:
                active_group.keys.remove(i)

        for area in context.screen.areas:
            area.tag_redraw()

        return {'FINISHED'}
