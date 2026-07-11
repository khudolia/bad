import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import blf
import math

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
        draw_rounded_rect(x1 + handle_width - 2, y1, box_width - (handle_width * 2) + 4, box_height, radius=0, color=base_color)
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