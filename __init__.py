bl_info = {
    "name": "Keyframe Grouping Tool",
    "author": "Andrii Khudolii",
    "version": (1, 0),
    "blender": (5, 0, 0),
    "location": "Dope Sheet",
    "description": "Group and transform keyframes together",
    "category": "Animation",
}

import bpy
import importlib
import sys

# 1. Safely handle Blender's aggressive caching with the nested path
if "anim_key_grouping.scripts.state" in sys.modules:
    from .scripts import state, properties, drawing, operators, ui
    importlib.reload(state)
    importlib.reload(properties)
    importlib.reload(drawing)
    importlib.reload(operators)
    importlib.reload(ui)
else:
    from .scripts import state, properties, drawing, operators, ui

# 2. Registration Classes
classes = (
    properties.AnimKeyReference,
    properties.AnimGroup,
    operators.ANIM_OT_create_clip_group,
    operators.ANIM_OT_delete_clip_group,
    operators.ANIM_OT_interactive_nest_tool,
    operators.ANIM_OT_select_single_object,
    operators.ANIM_OT_remove_object_from_group,
    operators.ANIM_OT_select_group_from_viewport,
    ui.DOPESHEET_PT_clip_info,
    ui.VIEW3D_PT_clip_list,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.anim_groups = bpy.props.CollectionProperty(type=properties.AnimGroup)
    bpy.types.DOPESHEET_MT_context_menu.append(ui.draw_dopesheet_context_menu)

    if "anim_clip_handler" not in bpy.app.driver_namespace:
        bpy.app.driver_namespace["anim_clip_handler"] = bpy.types.SpaceDopeSheetEditor.draw_handler_add(
            drawing.draw_clip_overlays, (), 'WINDOW', 'POST_PIXEL'
        )

    wm = bpy.context.window_manager
    if wm and wm.keyconfigs and wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Dopesheet', space_type='DOPESHEET_EDITOR')
        kmi = km.keymap_items.new("anim.interactive_nest_tool", 'LEFTMOUSE', 'PRESS')
        state.addon_keymaps.append((km, kmi))

def unregister():
    wm = bpy.context.window_manager
    if wm and wm.keyconfigs and wm.keyconfigs.addon:
        for km, kmi in state.addon_keymaps:
            km.keymap_items.remove(kmi)
    state.addon_keymaps.clear()

    if hasattr(bpy.types.DOPESHEET_MT_context_menu, "draw") and hasattr(bpy.types.DOPESHEET_MT_context_menu.draw, "_draw_funcs"):
        funcs = [f for f in bpy.types.DOPESHEET_MT_context_menu.draw._draw_funcs if f.__name__ == 'draw_dopesheet_context_menu']
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
    register()
