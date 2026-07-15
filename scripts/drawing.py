import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import blf
import math

# ==========================================
# UI SETTINGS
# ==========================================
SETTING_RADIUS = 6.0
SETTING_OUTLINE_WIDTH_BASE = 1.0
SETTING_OUTLINE_WIDTH_SEL = 10.0
SETTING_TOP_OFFSET = 50.0

SETTING_PADDING_X = 14.0

SETTING_TEXT_PADDING_X = 10.0
SETTING_TEXT_PADDING_Y = 24.0
SETTING_FONT_SIZE = 18

# ==========================================

def get_shader(mode='UNIFORM_COLOR'):
    try:
        return gpu.shader.from_builtin(mode)
    except ValueError:
        return gpu.shader.from_builtin('2D_UNIFORM_COLOR')

def get_rounded_rect_verts(x, y, width, height, radius):
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
    return verts

def draw_rounded_rect_solid(verts, color):
    shader = get_shader()
    center_x = sum(v[0] for v in verts) / len(verts)
    center_y = sum(v[1] for v in verts) / len(verts)
    fan_verts = [(center_x, center_y)] + verts + [verts[0]]
    inds = [(0, i, i + 1) for i in range(1, len(fan_verts) - 1)]

    batch = batch_for_shader(shader, 'TRIS', {"pos": fan_verts}, indices=inds)
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')

def draw_rounded_rect_outline(verts, color):
    shader = get_shader('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": verts})
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')

def draw_clip_overlays():
    context = bpy.context
    region = context.region
    if region.type != 'WINDOW': return

    from .state import clip_interaction
    isolated_uid = clip_interaction.get("isolated_group_uid", "")

    ui_scale = context.preferences.view.ui_scale

    for clip in context.scene.anim_groups:
        # Only render groups inside the current hierarchy level
        if clip.parent_uid != isolated_uid:
            continue

        start_px_coord = region.view2d.view_to_region(clip.start, 0, clip=False)
        end_px_coord = region.view2d.view_to_region(clip.end, 0, clip=False)
        if not start_px_coord or not end_px_coord: continue

        r_rad = SETTING_RADIUS * ui_scale
        pad = SETTING_PADDING_X * ui_scale

        x1 = start_px_coord[0] - pad
        x2 = end_px_coord[0] + pad

        y1 = -100 * ui_scale
        y2 = region.height - (SETTING_TOP_OFFSET * ui_scale)

        box_width = x2 - x1
        box_height = y2 - y1

        if box_width < 1 or box_height < 1: continue

        verts = get_rounded_rect_verts(x1, y1, box_width, box_height, r_rad)

        draw_rounded_rect_solid(verts, clip.color)

        if clip.is_selected:
            out_color = (1.0, 0.8, 0.0, 1.0) if clip.active_part != 'NONE' else (1.0, 1.0, 1.0, 0.9)
        else:
            out_color = (1.0, 1.0, 1.0, 0.5)

        draw_rounded_rect_outline(verts, out_color)

        font_id = 0
        blf.size(font_id, int(SETTING_FONT_SIZE * ui_scale))

        unique_actions = len(set(k.action_name for k in clip.keys))
        suffix = f" | {unique_actions}"
        base_name = clip.name

        available_width = box_width - (SETTING_TEXT_PADDING_X * 2 * ui_scale)
        full_text = f"{base_name}{suffix}"
        text_width = blf.dimensions(font_id, full_text)[0]
        text_to_draw = full_text

        if text_width > available_width:
            truncated_name = base_name
            while blf.dimensions(font_id, f"{truncated_name}...{suffix}")[0] > available_width and len(truncated_name) > 0:
                truncated_name = truncated_name[:-1]
            if len(truncated_name) == 0:
                text_to_draw = ""
            else:
                text_to_draw = f"{truncated_name}...{suffix}"

        if text_to_draw:
            text_x = x1 + (SETTING_TEXT_PADDING_X * ui_scale)
            text_y = y2 - (SETTING_TEXT_PADDING_Y * ui_scale)

            blf.position(font_id, text_x, text_y, 0)
            blf.enable(font_id, blf.SHADOW)
            blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 0.8)
            blf.shadow_offset(font_id, int(1 * ui_scale), int(-1 * ui_scale))
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            blf.draw(font_id, text_to_draw)
            blf.disable(font_id, blf.SHADOW)

    # Render Isolation Dimming Overlay around the parent
    if isolated_uid != "":
        iso_group = next((g for g in context.scene.anim_groups if g.uid == isolated_uid), None)
        if iso_group:
            iso_start_px = region.view2d.view_to_region(iso_group.start, 0, clip=False)
            iso_end_px = region.view2d.view_to_region(iso_group.end, 0, clip=False)

            if iso_start_px and iso_end_px:
                shader = get_shader('UNIFORM_COLOR')
                gpu.state.blend_set('ALPHA')
                shader.bind()
                shader.uniform_float("color", (0.0, 0.0, 0.0, 0.7))

                v_left = ((0, 0), (iso_start_px[0], 0), (iso_start_px[0], region.height), (0, region.height))
                batch_l = batch_for_shader(shader, 'TRIS', {"pos": v_left}, indices=((0, 1, 2), (0, 2, 3)))
                batch_l.draw(shader)

                v_right = ((iso_end_px[0], 0), (region.width, 0), (region.width, region.height), (iso_end_px[0], region.height))
                batch_r = batch_for_shader(shader, 'TRIS', {"pos": v_right}, indices=((0, 1, 2), (0, 2, 3)))
                batch_r.draw(shader)
                gpu.state.blend_set('NONE')