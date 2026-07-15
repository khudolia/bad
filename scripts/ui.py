import bpy


def get_all_keys(context, group):
    res = list(group.keys)
    for c in context.scene.anim_groups:
        if c.parent_uid == group.uid:
            res.extend(get_all_keys(context, c))
    return res


def draw_object_list(layout, context, group):
    box = layout.box()
    header_row = box.row(align=True)
    header_row.prop(group, "show_objects", icon='TRIA_DOWN' if group.show_objects else 'TRIA_RIGHT', text="",
                    emboss=False)
    header_row.label(text="Affected Objects")

    if group.show_objects:
        all_keys = get_all_keys(context, group)
        action_names = {k.action_name for k in all_keys}
        affected_objs = [
            obj for obj in context.scene.objects
            if obj.animation_data and obj.animation_data.action and obj.animation_data.action.name in action_names
        ]

        if not affected_objs:
            box.label(text="No valid objects found.")
        else:
            for obj in affected_objs:
                obj_row = box.row(align=True)

                sel_op = obj_row.operator("anim.select_single_object", text=obj.name, icon='OBJECT_DATA')
                sel_op.obj_name = obj.name

                rem_op = obj_row.operator("anim.remove_object_from_group", text="", icon='X')
                rem_op.obj_name = obj.name


def draw_dopesheet_context_menu(self, context):
    if context.space_data.type == 'DOPESHEET_EDITOR':
        self.layout.separator()
        self.layout.operator("anim.create_clip_group", icon='GROUP')


class DOPESHEET_PT_clip_info(bpy.types.Panel):
    bl_label = "Group Information"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Clip Tool"

    def draw(self, context):
        layout = self.layout
        active_group = None

        from .state import clip_interaction
        isolated_uid = clip_interaction.get("isolated_group_uid", "")

        if isolated_uid != "":
            box = layout.box()
            iso_group = next((g for g in context.scene.anim_groups if g.uid == isolated_uid), None)
            iso_name = iso_group.name if iso_group else "Group"
            box.label(text=f"Editing: {iso_name}", icon='LOCKED')
            box.operator("anim.exit_isolation", text="Step Out (Exit Group)", icon='LOOP_BACK')
            layout.separator()

        for group in context.scene.anim_groups:
            if group.is_selected:
                active_group = group
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

        draw_object_list(layout, context, active_group)

        layout.separator()

        box = layout.box()
        box.label(text="Danger Zone", icon='ERROR')
        row = box.row(align=True)

        op_del_group = row.operator("anim.delete_clip_group", text="Remove Group Only")
        op_del_group.delete_keys = False
        op_del_group.group_uid = active_group.uid

        op_del_keys = row.operator("anim.delete_clip_group", text="Delete Group + Keys")
        op_del_keys.delete_keys = True
        op_del_keys.group_uid = active_group.uid


class VIEW3D_PT_clip_list(bpy.types.Panel):
    bl_label = "Animation Groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Clip Tool"

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "anim_groups")

    def draw(self, context):
        layout = self.layout
        groups = context.scene.anim_groups

        if not groups:
            layout.label(text="No groups created.", icon='INFO')
            return

        from .state import clip_interaction
        isolated_uid = clip_interaction.get("isolated_group_uid", "")

        if isolated_uid != "":
            iso_group = next((g for g in groups if g.uid == isolated_uid), None)
            iso_name = iso_group.name if iso_group else "Group"
            row = layout.row(align=True)
            row.operator("anim.exit_isolation", text=f"Exit {iso_name}", icon='LOOP_BACK')
            layout.separator()

        col = layout.column(align=True)
        drawn_any = False

        for group in groups:
            # Only draw groups belonging to current isolated layer
            if group.parent_uid != isolated_uid:
                continue

            drawn_any = True
            row = col.row(align=True)

            color_col = row.column()
            color_col.enabled = False
            color_col.prop(group, "color", text="")

            button_text = f"► {group.name}" if group.is_selected else group.name

            op = row.operator("anim.select_group_from_viewport", text=button_text)
            op.group_uid = group.uid

            if group.is_selected:
                row.active = True
                draw_object_list(col, context, group)

        if not drawn_any:
            layout.label(text="No sub-groups.", icon='INFO')