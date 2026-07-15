import bpy


class AnimKeyReference(bpy.types.PropertyGroup):
    action_name: bpy.props.StringProperty()
    data_path: bpy.props.StringProperty()
    array_index: bpy.props.IntProperty()
    kf_index: bpy.props.IntProperty()
    orig_frame: bpy.props.FloatProperty()


class AnimGroup(bpy.types.PropertyGroup):
    uid: bpy.props.StringProperty()
    parent_uid: bpy.props.StringProperty(default="")

    name: bpy.props.StringProperty(name="Group Name", default="New Group")
    start: bpy.props.FloatProperty(name="Start")
    end: bpy.props.FloatProperty(name="End")

    # Used internally during recursive modal dragging
    orig_start: bpy.props.FloatProperty()
    orig_end: bpy.props.FloatProperty()

    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', default=(0.2, 0.6, 1.0), size=3, min=0.0, max=1.0
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

    show_objects: bpy.props.BoolProperty(name="Show Objects", default=False)


def register_clipboard():
    bpy.types.Scene.anim_group_clipboard = bpy.props.StringProperty(
        name="Group Clipboard",
        default="{}"
    )


def unregister_clipboard():
    if hasattr(bpy.types.Scene, "anim_group_clipboard"):
        del bpy.types.Scene.anim_group_clipboard