set(Namespace_SRCS
        freecad/maxproframe/resources/icons/corner.svg
        freecad/maxproframe/resources/icons/splitcurve.svg
        freecad/maxproframe/resources/icons/warehouse_profiles.svg
        freecad/maxproframe/resources/icons/trim_extend.svg
        freecad/maxproframe/resources/icons/metalwb.svg
        freecad/maxproframe/resources/icons/line.svg
        freecad/maxproframe/resources/icons/corner-end-miter.svg
        freecad/maxproframe/resources/icons/discretize.svg
        freecad/maxproframe/resources/icons/joincurve.svg
        freecad/maxproframe/resources/icons/overlap.svg
        freecad/maxproframe/resources/icons/box.svg
        freecad/maxproframe/resources/icons/bom.svg
        freecad/maxproframe/resources/icons/parts_list.svg
        freecad/maxproframe/resources/icons/corner-coped-type.svg
        freecad/maxproframe/resources/icons/corner-simple-type.svg
        freecad/maxproframe/resources/icons/corner-end-trim.svg
        freecad/maxproframe/resources/icons/list-remove.svg
        freecad/maxproframe/resources/icons/extendcurve.svg
        freecad/maxproframe/resources/icons/list-add.svg
        freecad/maxproframe/resources/icons/extrude-cutout.svg

        freecad/maxproframe/resources/images/profiles/Metal/HEB_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Square_Hollow.png
        freecad/maxproframe/resources/images/profiles/Metal/HEM_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/UPN_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Round_Bar.png
        freecad/maxproframe/resources/images/profiles/Metal/UPE.png
        freecad/maxproframe/resources/images/profiles/Metal/HEA.png
        freecad/maxproframe/resources/images/profiles/Metal/HEA_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/HEB.png
        freecad/maxproframe/resources/images/profiles/Metal/IPN_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/IPN.png
        freecad/maxproframe/resources/images/profiles/Metal/UPN.png
        freecad/maxproframe/resources/images/profiles/Metal/Square_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Unequal_Leg_Angles.png
        freecad/maxproframe/resources/images/profiles/Metal/Flat_Sections.png
        freecad/maxproframe/resources/images/profiles/Metal/IPE.png
        freecad/maxproframe/resources/images/profiles/Metal/UPE_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Unequal_Leg_Angles_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Rectangular_Hollow_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/HEM.png
        freecad/maxproframe/resources/images/profiles/Metal/Square_Hollow_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Equal_Leg_Angles_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Equal_Leg_Angles.png
        freecad/maxproframe/resources/images/profiles/Metal/Rectangular_Hollow.png
        freecad/maxproframe/resources/images/profiles/Metal/IPE_Fillet.png
        freecad/maxproframe/resources/images/profiles/Metal/Pipe.png
        freecad/maxproframe/resources/images/profiles/Metal/Square.png
        freecad/maxproframe/resources/images/profiles/Warehouse.png
        freecad/maxproframe/resources/images/profiles/Custom_Profile.png
        freecad/maxproframe/resources/images/profiles/Metal/Custom_Profile.png
        freecad/maxproframe/resources/images/profiles/Metal/T-Slot.png
        freecad/maxproframe/resources/images/profiles/Metal/T-Slot_1-Slot.png
        freecad/maxproframe/resources/images/profiles/Metal/T-Slot_2-Slots.png
        freecad/maxproframe/resources/images/profiles/Metal/T-Slot_2-Slots_Opp.png
        freecad/maxproframe/resources/images/profiles/Metal/T-Slot_3-Slots.png
        freecad/maxproframe/resources/images/profiles/Metal/V-Slot.png

        freecad/maxproframe/resources/help/library-manager.md
        freecad/maxproframe/resources/help/library-manager.es.md

        freecad/maxproframe/resources/ui/create_trimmed_profiles.ui
        freecad/maxproframe/resources/ui/extend_cut.ui
        freecad/maxproframe/resources/ui/create_profiles.ui

        freecad/maxproframe/resources/profiles/metal.json

        freecad/maxproframe/version.py
        freecad/maxproframe/ff_tools.py
        freecad/maxproframe/create_trimmed_profiles_tool.py
        freecad/maxproframe/edit_profile_tool.py
        freecad/maxproframe/profile.py
        freecad/maxproframe/_utils.py
        freecad/maxproframe/parametric_line.py
        freecad/maxproframe/create_end_miter_tool.py
        freecad/maxproframe/create_extend_cut_tool.py
        freecad/maxproframe/trimmed_profile.py
        freecad/maxproframe/init_gui.py
        freecad/maxproframe/create_profiles_tool.py
        freecad/maxproframe/utilities.py
)

SOURCE_GROUP("" FILES ${Namespace_SRCS})

ADD_CUSTOM_TARGET(SEARCHBAR ALL
        SOURCES ${Namespace_SRCS}
)

fc_copy_sources(SEARCHBAR "${CMAKE_BINARY_DIR}/Mod/FrameForge" ${Namespace_SRCS})

INSTALL(
    FILES
        ${Namespace_SRCS}
    DESTINATION
        Mod/SearchBar
)
