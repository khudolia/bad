import bpy

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

class VIEW3D_PT_clip_list(bpy.types.Panel):
    bl_label = "Animation Groups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Clip Tool"

    def draw(self, context):
        layout = self.layout
        groups = context.scene.anim_groups

        if not groups:
            layout.label(text="No groups created.", icon='INFO')
            return

        col = layout.column(align=True)
        for i, group in enumerate(groups):
            row = col.row(align=True)

            # Draw color picker (disabled to act purely as an indicator)
            color_col = row.column()
            color_col.enabled = False
            color_col.prop(group, "color", text="")

            # Draw selector button
            op = row.operator("anim.select_group_from_viewport", text=group.name)
            op.group_idx = i

            # Highlight button if actively selected
            if group.is_selected:
                row.active = True
                op.text = f"► {group.name}"

def draw_dopesheet_context_menu(self, context):
    self.layout.separator()
    self.layout.operator("anim.create_clip_group", icon='GROUP')