import bpy
import colorsys
import uuid
from .state import clip_interaction
import re

_is_clamping = False


def ensure_uids(groups):
    for g in groups:
        if not g.uid:
            g.uid = str(uuid.uuid4())


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


def get_all_keys(context, group):
    res = list(group.keys)
    for c in context.scene.anim_groups:
        if c.parent_uid == group.uid:
            res.extend(get_all_keys(context, c))
    return res


def delete_group_recursive(context, uid, delete_keys=False):
    groups = context.scene.anim_groups
    children_uids = [g.uid for g in groups if g.parent_uid == uid]
    for c_uid in children_uids:
        delete_group_recursive(context, c_uid, delete_keys)

    idx = next((i for i, g in enumerate(groups) if g.uid == uid), -1)
    if idx != -1:
        group = groups[idx]
        if delete_keys:
            fcu_maps = {}
            keys_to_delete = {}
            for k_ref in group.keys:
                action = bpy.data.actions.get(k_ref.action_name)
                if not action: continue
                if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)
                fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
                if fcu:
                    fcu_key = (action.name, fcu.data_path, fcu.array_index)
                    if fcu_key not in keys_to_delete: keys_to_delete[fcu_key] = {'fcu': fcu, 'indices': []}
                    keys_to_delete[fcu_key]['indices'].append(k_ref.kf_index)
            for data in keys_to_delete.values():
                fcu = data['fcu']
                indices = data['indices']
                indices.sort(reverse=True)
                for i in indices:
                    if i < len(fcu.keyframe_points):
                        fcu.keyframe_points.remove(fcu.keyframe_points[i])
        groups.remove(idx)


@bpy.app.handlers.persistent
def clamp_isolated_keyframes(scene, depsgraph):
    global _is_clamping
    if _is_clamping: return

    from .state import clip_interaction
    isolated_uid = clip_interaction.get("isolated_group_uid", "")
    if not isolated_uid: return

    group = next((g for g in scene.anim_groups if g.uid == isolated_uid), None)
    if not group: return

    g_start = group.start
    g_end = group.end

    _is_clamping = True
    try:
        for action in bpy.data.actions:
            fcu_map = get_fcu_map(action)
            for fcu in fcu_map.values():
                if fcu.lock: continue
                for kf in fcu.keyframe_points:
                    if kf.select_control_point:
                        if kf.co[0] < g_start:
                            kf.co[0] = g_start
                        elif kf.co[0] > g_end:
                            kf.co[0] = g_end
    finally:
        _is_clamping = False


def sync_object_selection(context, group):
    for obj in context.scene.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass

    if not group: return
    action_names = {k_ref.action_name for k_ref in get_all_keys(context, group)}

    for obj in context.scene.objects:
        if obj.animation_data and obj.animation_data.action:
            if obj.animation_data.action.name in action_names:
                if not obj.hide_get() and not obj.hide_viewport:
                    try:
                        obj.select_set(True)
                        context.view_layer.objects.active = obj
                    except RuntimeError:
                        pass


def select_group_keyframes_safe(context, group):
    for action in bpy.data.actions:
        fcu_map = get_fcu_map(action)
        for fcu in fcu_map.values():
            for kf in fcu.keyframe_points:
                kf.select_control_point = False

    if not group: return
    all_keys = get_all_keys(context, group)
    fcu_maps = {}

    for k_ref in all_keys:
        action = bpy.data.actions.get(k_ref.action_name)
        if not action: continue
        if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)

        fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
        if fcu and k_ref.kf_index < len(fcu.keyframe_points):
            fcu.keyframe_points[k_ref.kf_index].select_control_point = True


class ANIM_OT_duplicate_group(bpy.types.Operator):
    bl_idname = "anim.duplicate_group"
    bl_label = "Duplicate Active Group"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        if not hasattr(context.scene, "anim_groups"): return False
        return any(g.is_selected for g in context.scene.anim_groups)

    def execute(self, context):
        ensure_uids(context.scene.anim_groups)
        active_group = next((g for g in context.scene.anim_groups if g.is_selected), None)
        if not active_group: return {'CANCELLED'}

        orig_name = str(active_group.name)
        orig_color = list(active_group.color)
        orig_depth = active_group.vertical_depth
        orig_mode = active_group.responsive_mode
        orig_start = active_group.start
        orig_end = active_group.end
        orig_parent_uid = active_group.parent_uid
        duration = orig_end - orig_start

        keys_to_duplicate = []
        fcu_maps = {}

        for k_ref in active_group.keys:
            action = bpy.data.actions.get(k_ref.action_name)
            if not action: continue
            if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)

            fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
            if fcu and k_ref.kf_index < len(fcu.keyframe_points):
                kf = fcu.keyframe_points[k_ref.kf_index]
                keys_to_duplicate.append({
                    'fcu': fcu, 'co': (kf.co[0], kf.co[1]), 'hl': (kf.handle_left[0], kf.handle_left[1]),
                    'hr': (kf.handle_right[0], kf.handle_right[1]), 'interp': kf.interpolation,
                    'easing': getattr(kf, 'easing', 'AUTO'), 'hlt': kf.handle_left_type,
                    'hrt': kf.handle_right_type, 'amp': getattr(kf, 'amplitude', 0.0),
                    'per': getattr(kf, 'period', 0.0), 'back': getattr(kf, 'back', 0.0),
                    'type': getattr(kf, 'type', 'KEYFRAME')
                })

        if not keys_to_duplicate:
            self.report({'WARNING'}, "Original group has no valid keyframes.")
            return {'CANCELLED'}

        current_frame = float(context.scene.frame_current)
        offset = current_frame - orig_start

        for action in bpy.data.actions:
            for fcu in get_fcu_map(action).values():
                for kf in fcu.keyframe_points:
                    kf.select_control_point = False
                    kf.select_left_handle = False
                    kf.select_right_handle = False

        modified_fcus = set()
        for d in keys_to_duplicate:
            fcu = d['fcu']
            new_time = d['co'][0] + offset
            new_kf = fcu.keyframe_points.insert(new_time, d['co'][1])
            new_kf.interpolation = d['interp']
            new_kf.handle_left_type = d['hlt']
            new_kf.handle_right_type = d['hrt']
            new_kf.handle_left = (d['hl'][0] + offset, d['hl'][1])
            new_kf.handle_right = (d['hr'][0] + offset, d['hr'][1])
            if hasattr(new_kf, 'easing'): new_kf.easing = d['easing']
            if hasattr(new_kf, 'amplitude'): new_kf.amplitude = d['amp']
            if hasattr(new_kf, 'period'): new_kf.period = d['per']
            if hasattr(new_kf, 'back'): new_kf.back = d['back']
            if hasattr(new_kf, 'type'): new_kf.type = d['type']
            new_kf.select_control_point = True
            new_kf.select_left_handle = True
            new_kf.select_right_handle = True
            modified_fcus.add(fcu)

        for fcu in modified_fcus: fcu.update()

        new_group = context.scene.anim_groups.add()
        new_group.uid = str(uuid.uuid4())
        new_group.parent_uid = orig_parent_uid

        base_name = orig_name
        match_orig = re.search(r" \((\d+)\)$", orig_name)
        if match_orig: base_name = orig_name[:match_orig.start()]

        highest_num = 0
        for g in context.scene.anim_groups:
            if g.name == base_name: continue
            if g.name.startswith(base_name + " (") and g.name.endswith(")"):
                suffix_str = g.name[len(base_name) + 2: -1]
                if suffix_str.isdigit(): highest_num = max(highest_num, int(suffix_str))

        new_group.name = f"{base_name} ({highest_num + 1})"
        new_group.color = orig_color
        new_group.vertical_depth = orig_depth
        new_group.responsive_mode = orig_mode
        new_group.start = orig_start + offset
        new_group.end = orig_end + offset

        for action in bpy.data.actions:
            fcu_map = get_fcu_map(action)
            for path, fcu in fcu_map.items():
                for i, kf in enumerate(fcu.keyframe_points):
                    if kf.select_control_point:
                        k_ref = new_group.keys.add()
                        k_ref.action_name = action.name
                        k_ref.data_path = fcu.data_path
                        k_ref.array_index = fcu.array_index
                        k_ref.kf_index = i
                        k_ref.orig_frame = kf.co[0]

        for g in context.scene.anim_groups: g.is_selected = False
        new_group.is_selected = True

        for area in context.screen.areas: area.tag_redraw()
        return {'FINISHED'}


class ANIM_OT_create_clip_group(bpy.types.Operator):
    bl_idname = "anim.create_clip_group"
    bl_label = "Group Selected Keys"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ensure_uids(context.scene.anim_groups)
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
                            'action': action.name, 'path': fcu.data_path,
                            'array_idx': fcu.array_index, 'kf_idx': i, 'frame': co_x
                        })
                        selected_key_ids.add(f"{action.name}_{fcu.data_path}{fcu.array_index}_{i}")

        if not selected_keys_data:
            self.report({'WARNING'}, "No selected keyframes found.")
            return {'CANCELLED'}

        parent_uid = clip_interaction.get("isolated_group_uid", "")

        # 1. Delete sibling subgroups occupying these keys
        groups_to_delete = []
        for group in context.scene.anim_groups:
            if group.parent_uid == parent_uid:
                for k_ref in group.keys:
                    k_id = f"{k_ref.action_name}_{k_ref.data_path}{k_ref.array_index}_{k_ref.kf_index}"
                    if k_id in selected_key_ids:
                        groups_to_delete.append(group.uid)
                        break

        for uid in groups_to_delete:
            delete_group_recursive(context, uid)

        # 2. Extract ownership from parent group
        if parent_uid:
            parent = next((g for g in context.scene.anim_groups if g.uid == parent_uid), None)
            if parent:
                for i in range(len(parent.keys) - 1, -1, -1):
                    k_ref = parent.keys[i]
                    k_id = f"{k_ref.action_name}_{k_ref.data_path}{k_ref.array_index}_{k_ref.kf_index}"
                    if k_id in selected_key_ids:
                        parent.keys.remove(i)

        if min_frame == max_frame: max_frame = min_frame + 1.0

        new_group = context.scene.anim_groups.add()
        new_group.uid = str(uuid.uuid4())
        new_group.parent_uid = parent_uid

        group_count = len(context.scene.anim_groups)
        hue = (group_count * 0.618033988749895) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.6, 0.9)
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

        for area in context.screen.areas: area.tag_redraw()
        return {'FINISHED'}


class ANIM_OT_delete_clip_group(bpy.types.Operator):
    bl_idname = "anim.delete_clip_group"
    bl_label = "Delete Group"
    bl_options = {'REGISTER', 'UNDO'}

    delete_keys: bpy.props.BoolProperty(default=False)
    group_uid: bpy.props.StringProperty()

    def execute(self, context):
        ensure_uids(context.scene.anim_groups)
        delete_group_recursive(context, self.group_uid, self.delete_keys)

        if clip_interaction.get("active_group_uid") == self.group_uid:
            clip_interaction["active_group_uid"] = ""

        iso_uid = clip_interaction.get("isolated_group_uid", "")
        if iso_uid != "":
            if not any(g.uid == iso_uid for g in context.scene.anim_groups):
                clip_interaction["isolated_group_uid"] = ""

        for area in context.screen.areas: area.tag_redraw()
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

    def capture_keys(self, context, group):
        fcu_maps = {}
        for k_ref in group.keys:
            action = bpy.data.actions.get(k_ref.action_name)
            if not action: continue
            if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)

            fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
            if fcu and k_ref.kf_index < len(fcu.keyframe_points):
                k_ref.orig_frame = fcu.keyframe_points[k_ref.kf_index].co[0]

        group.orig_start = group.start
        group.orig_end = group.end

        for child in context.scene.anim_groups:
            if child.parent_uid == group.uid:
                self.capture_keys(context, child)

    def update_keys_recursive(self, context, group, master_orig_start, master_orig_end, mode, parent_new_start,
                              parent_new_end):
        orig_length = master_orig_end - master_orig_start
        if orig_length <= 0: orig_length = 1.0
        new_length = parent_new_end - parent_new_start
        fcu_maps = {}

        for k_ref in group.keys:
            action = bpy.data.actions.get(k_ref.action_name)
            if not action: continue
            if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)

            fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
            if not fcu or k_ref.kf_index >= len(fcu.keyframe_points): continue

            kf = fcu.keyframe_points[k_ref.kf_index]
            old_frame = kf.co[0]

            if mode == 'PROPORTIONAL':
                t = (k_ref.orig_frame - master_orig_start) / orig_length
                new_frame = parent_new_start + (t * new_length)
            else:
                new_frame = k_ref.orig_frame + (parent_new_start - master_orig_start)

            delta = new_frame - old_frame
            kf.co[0] = new_frame
            kf.handle_left[0] += delta
            kf.handle_right[0] += delta

        for child in context.scene.anim_groups:
            if child.parent_uid == group.uid:
                c_orig_start = child.orig_start
                c_orig_end = child.orig_end

                if mode == 'PROPORTIONAL':
                    t_s = (c_orig_start - master_orig_start) / orig_length
                    child.start = parent_new_start + (t_s * new_length)
                    t_e = (c_orig_end - master_orig_start) / orig_length
                    child.end = parent_new_start + (t_e * new_length)
                else:
                    offset = parent_new_start - master_orig_start
                    child.start = c_orig_start + offset
                    child.end = c_orig_end + offset

                self.update_keys_recursive(context, child, master_orig_start, master_orig_end, mode, parent_new_start,
                                           parent_new_end)

    def invoke(self, context, event):
        if context.area.type != 'DOPESHEET_EDITOR': return {'PASS_THROUGH'}
        window_region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not window_region: return {'PASS_THROUGH'}

        mx = event.mouse_x - window_region.x
        my = event.mouse_y - window_region.y

        if not (0 <= mx <= window_region.width and 0 <= my <= window_region.height):
            return {'PASS_THROUGH'}

        view2d = window_region.view2d
        frame, _ = view2d.region_to_view(mx, my)

        ensure_uids(context.scene.anim_groups)
        isolated_uid = clip_interaction.get("isolated_group_uid", "")

        hit_detected = False
        clip_interaction["active_group_uid"] = ""

        import time
        current_time = time.time()
        is_double_click = (current_time - clip_interaction["last_click_time"]) < 0.3

        for idx, group in enumerate(context.scene.anim_groups):
            if group.parent_uid != isolated_uid:
                continue

            start_px_coord = view2d.view_to_region(group.start, 0, clip=False)
            end_px_coord = view2d.view_to_region(group.end, 0, clip=False)
            if not start_px_coord or not end_px_coord: continue

            x1, _ = start_px_coord
            x2, _ = end_px_coord
            y2 = window_region.height - 50
            y1 = y2 - (group.vertical_depth * 34)

            if y1 <= my <= y2 and (x1 - 15) <= mx <= (x2 + 15):
                hit_detected = True
                clip_interaction["active_group_uid"] = group.uid

                if is_double_click:
                    clip_interaction["isolated_group_uid"] = group.uid
                    bpy.ops.action.select_all(action='DESELECT')

                    all_keys = get_all_keys(context, group)
                    fcu_maps = {}
                    group_paths = {f"{k.action_name}_{k.data_path}_{k.array_index}" for k in all_keys}

                    min_kf, max_kf = None, None
                    min_frame, max_frame = float('inf'), float('-inf')

                    for k_ref in all_keys:
                        action = bpy.data.actions.get(k_ref.action_name)
                        if not action: continue
                        if action.name not in fcu_maps: fcu_maps[action.name] = get_fcu_map(action)

                        fcu = fcu_maps[action.name].get(k_ref.data_path + str(k_ref.array_index))
                        if fcu and k_ref.kf_index < len(fcu.keyframe_points):
                            kf = fcu.keyframe_points[k_ref.kf_index]
                            kf.select_control_point = True

                            if kf.co[0] < min_frame: min_frame, min_kf = kf.co[0], kf
                            if kf.co[0] > max_frame: max_frame, max_kf = kf.co[0], kf

                    if min_kf: min_kf.co[0] -= 1
                    if max_kf and max_kf != min_kf: max_kf.co[0] += 1

                    try:
                        bpy.ops.action.view_selected()
                    except RuntimeError:
                        pass
                    finally:
                        if min_kf: min_kf.co[0] += 1
                        if max_kf and max_kf != min_kf: max_kf.co[0] -= 1

                    for action in bpy.data.actions:
                        action_fcu_map = get_fcu_map(action)
                        for fcu in action_fcu_map.values():
                            path_id = f"{action.name}_{fcu.data_path}_{fcu.array_index}"
                            fcu.lock = path_id not in group_paths

                    context.area.tag_redraw()
                    return {'CANCELLED'}

                clip_interaction["orig_start"] = group.start
                clip_interaction["orig_end"] = group.end
                for g in context.scene.anim_groups: g.is_selected = False
                group.is_selected = True

                select_group_keyframes_safe(context, group)
                sync_object_selection(context, group)

                box_width = x2 - x1
                ui_scale = context.preferences.view.ui_scale
                handle_width = min(20 * ui_scale, box_width * 0.15)

                if mx < x1 + handle_width:
                    clip_interaction["drag_mode"] = 'LEFT'
                    group.active_part = 'LEFT'
                    clip_interaction["drag_offset"] = frame - group.start
                elif mx > x2 - handle_width:
                    clip_interaction["drag_mode"] = 'RIGHT'
                    group.active_part = 'RIGHT'
                    clip_interaction["drag_offset"] = frame - group.end
                else:
                    clip_interaction["drag_mode"] = 'BODY'
                    group.active_part = 'BODY'
                    clip_interaction["drag_offset"] = frame - group.start

                self.capture_keys(context, group)
                break

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            clip_interaction["last_click_time"] = current_time

        if hit_detected:
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def modal(self, context, event):
        if not context.area or context.area.type != 'DOPESHEET_EDITOR': return {'CANCELLED'}
        window_region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not window_region: return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            clip_interaction["drag_mode"] = 'NONE'
            active_uid = clip_interaction.get("active_group_uid", "")
            if active_uid:
                group = next((g for g in context.scene.anim_groups if g.uid == active_uid), None)
                if group: group.active_part = 'NONE'
            context.area.tag_redraw()
            return {'FINISHED'}

        elif event.type == 'MOUSEMOVE':
            active_uid = clip_interaction.get("active_group_uid", "")
            if clip_interaction["drag_mode"] != 'NONE' and active_uid:
                view2d = window_region.view2d
                mx = event.mouse_x - window_region.x
                my = event.mouse_y - window_region.y
                frame, _ = view2d.region_to_view(mx, my)

                group = next((g for g in context.scene.anim_groups if g.uid == active_uid), None)
                if not group: return {'RUNNING_MODAL'}

                target_frame = round(frame - clip_interaction["drag_offset"])
                orig_start = clip_interaction["orig_start"]

                if group.responsive_mode == 'CONSTANT':
                    def get_max_offset(g, o_start):
                        m = max((k.orig_frame - o_start for k in g.keys), default=0)
                        for c in context.scene.anim_groups:
                            if c.parent_uid == g.uid: m = max(m, get_max_offset(c, o_start))
                        return m

                    orig_length = clip_interaction["orig_end"] - orig_start
                    keys_max_offset = get_max_offset(group, orig_start)
                    if keys_max_offset == 0: keys_max_offset = orig_length

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

                self.update_keys_recursive(context, group, orig_start, clip_interaction["orig_end"],
                                           group.responsive_mode, group.start, group.end)
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}


class ANIM_OT_select_group_from_viewport(bpy.types.Operator):
    bl_idname = "anim.select_group_from_viewport"
    bl_label = "Select Anim Group"
    bl_options = {'REGISTER', 'UNDO'}

    group_uid: bpy.props.StringProperty()

    def execute(self, context):
        group = next((g for g in context.scene.anim_groups if g.uid == self.group_uid), None)
        if not group: return {'CANCELLED'}

        for g in context.scene.anim_groups: g.is_selected = False
        group.is_selected = True

        action_names = {k_ref.action_name for k_ref in get_all_keys(context, group)}

        bpy.ops.object.select_all(action='DESELECT')
        for obj in context.scene.objects:
            if obj.animation_data and obj.animation_data.action:
                if obj.animation_data.action.name in action_names:
                    obj.select_set(True)
                    context.view_layer.objects.active = obj

        select_group_keyframes_safe(context, group)
        context.scene.frame_current = int(group.start)

        dopesheet_area = next((a for a in context.screen.areas if a.type == 'DOPESHEET_EDITOR'), None)
        if dopesheet_area:
            dopesheet_region = next((r for r in dopesheet_area.regions if r.type == 'WINDOW'), None)
            if dopesheet_region:
                with context.temp_override(area=dopesheet_area, region=dopesheet_region):
                    try:
                        bpy.ops.action.view_frame()
                    except RuntimeError:
                        pass

        for area in context.screen.areas: area.tag_redraw()
        return {'FINISHED'}


class ANIM_OT_select_single_object(bpy.types.Operator):
    bl_idname = "anim.select_single_object"
    bl_label = "Select Object"
    bl_options = {'UNDO'}

    obj_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.scene.objects.get(self.obj_name)
        if not obj: return {'CANCELLED'}

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

        if not obj or not active_group: return {'CANCELLED'}
        if not obj.animation_data or not obj.animation_data.action: return {'CANCELLED'}

        action_name = obj.animation_data.action.name

        def remove_action_from_group(g):
            for i in range(len(g.keys) - 1, -1, -1):
                if g.keys[i].action_name == action_name:
                    g.keys.remove(i)
            for c in context.scene.anim_groups:
                if c.parent_uid == g.uid:
                    remove_action_from_group(c)

        remove_action_from_group(active_group)

        for area in context.screen.areas: area.tag_redraw()
        return {'FINISHED'}


class ANIM_OT_exit_isolation(bpy.types.Operator):
    bl_idname = "anim.exit_isolation"
    bl_label = "Exit Group Edit"
    bl_options = {'UNDO'}

    _timer = None
    _step = 0
    _target_uid = ""

    def execute(self, context):
        from .state import clip_interaction
        isolated_uid = clip_interaction.get("isolated_group_uid", "")

        if isolated_uid:
            group = next((g for g in context.scene.anim_groups if g.uid == isolated_uid), None)
            if group:
                clip_interaction["isolated_group_uid"] = group.parent_uid
            else:
                clip_interaction["isolated_group_uid"] = ""

        self._target_uid = clip_interaction["isolated_group_uid"]

        for action in bpy.data.actions:
            action_fcu_map = get_fcu_map(action)
            for fcu in action_fcu_map.values():
                fcu.lock = False

        if self._target_uid:
            target_group = next((g for g in context.scene.anim_groups if g.uid == self._target_uid), None)
            if target_group:
                all_keys = get_all_keys(context, target_group)
                group_paths = {f"{k.action_name}_{k.data_path}_{k.array_index}" for k in all_keys}

                for action in bpy.data.actions:
                    action_fcu_map = get_fcu_map(action)
                    for fcu in action_fcu_map.values():
                        path_id = f"{action.name}_{fcu.data_path}_{fcu.array_index}"
                        fcu.lock = path_id not in group_paths

        for area in context.screen.areas: area.tag_redraw()

        self._step = 0
        self._timer = context.window_manager.event_timer_add(0.05, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._step < 1:
                self._step += 1
                return {'RUNNING_MODAL'}

            context.window_manager.event_timer_remove(self._timer)

            dopesheet_area = next((a for a in context.screen.areas if a.type == 'DOPESHEET_EDITOR'), None)
            if dopesheet_area:
                dopesheet_region = next((r for r in dopesheet_area.regions if r.type == 'WINDOW'), None)
                space = dopesheet_area.spaces.active
                ds = space.dopesheet

                if dopesheet_region:
                    had_only_selected = ds.show_only_selected
                    ds.show_only_selected = False
                    try:
                        with context.temp_override(window=context.window, area=dopesheet_area, region=dopesheet_region):
                            bpy.ops.action.select_all(action='SELECT')
                            bpy.ops.action.view_all()
                            bpy.ops.action.select_all(action='DESELECT')
                    except RuntimeError as e:
                        pass
                    finally:
                        ds.show_only_selected = had_only_selected

            if self._target_uid:
                group = next((g for g in context.scene.anim_groups if g.uid == self._target_uid), None)
                if group: select_group_keyframes_safe(context, group)

            for area in context.screen.areas: area.tag_redraw()
            return {'FINISHED'}
        return {'PASS_THROUGH'}