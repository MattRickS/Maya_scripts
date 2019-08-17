import maya.cmds as cmds

# XXX: It's not super important, but only class names in python should use
# CamelCase, every variable/function should use snake_case. It's part of the
# python PEP style guides.


def align(source, target):
    # type: (str, str) -> list[float]
    matrix = cmds.xform(target, query=True, worldSpace=True, matrix=True)
    cmds.xform(source, worldSpace=True, matrix=matrix)
    return matrix


def copy_joint_with_locator(source_joint, prefix):
    # type: (str, str) -> tuple[str, str]
    start_loc = cmds.spaceLocator(name=prefix + "Loc")[0]
    # XXX: creating a constraint to position the locator is a little overkill
    # and may have unintended side effects - safer to just copy it's matrix. Can
    # put it in a function so that you can re-use it easily.
    align(start_loc, source_joint)

    cmds.select(clear=True)
    start_w_joint = cmds.joint(name=prefix + "WireJoint")
    cmds.parent(start_w_joint, start_loc, relative=True)
    return start_loc, start_w_joint


def create_follicle(prefix, shape, u_pos, v_pos, num=1):
    # type: (str, str, float, float, int) -> tuple[str, str]
    fol_shape = cmds.createNode("follicle")
    fol_trans = cmds.listRelatives(fol_shape, parent=True)[0]
    fol_trans = cmds.rename(fol_trans, prefix + "_follicle_{:02d}".format(num))
    fol_shape = cmds.listRelatives(fol_trans, shapes=True)[0]
    fol_shape = cmds.rename(
        fol_shape, prefix + "_follicleShape_{:02d}".format(num)
    )

    cmds.connectAttr(
        shape + ".worldMatrix[0]", fol_shape + ".inputWorldMatrix"
    )
    cmds.connectAttr(shape + ".local", fol_shape + ".inputSurface")
    cmds.connectAttr(fol_shape + ".outTranslate", fol_trans + ".translate")
    cmds.connectAttr(fol_shape + ".outRotate", fol_trans + ".rotate")

    cmds.setAttr(fol_shape + ".parameterU", v_pos)
    cmds.setAttr(fol_shape + ".parameterV", u_pos)
    return fol_trans, fol_shape


def add_joint(prefix, start_joint, number_of_bones=3):
    # type: (str, str, int) -> str
    # TODO: add if statement to test for selected and joint
    # XXX: Be explicit with which relatives are needed. Also, this only gets the NEXT
    # joint, it doesn't walk through all joints, is that the intended behaviour?
    end_joint = cmds.listRelatives(start_joint, children=True)[0]
    # XXX: This just gets the end position, but the variable is called "length",
    # should it be calculating the distance between start and end?
    s_len = cmds.getAttr(end_joint + ".translateX")

    start_point = cmds.xform(start_joint, query=True, worldSpace=True, translation=True)
    end_point = cmds.xform(end_joint, query=True, worldSpace=True, translation=True)

    # create start + end locators, bones to skin the wire to, and an empty group
    # XXX: Duplicated behaviour is best separate into a method for re-use
    start_loc, start_w_joint = copy_joint_with_locator(start_joint, "start")
    end_loc, end_w_joint = copy_joint_with_locator(end_joint, "end")

    s_grp = cmds.group(empty=True, name=prefix + "_stretchPlaneGrp")
    align(s_grp, start_loc)

    # create NURBS plane and CV curve. Group everything into the new sGrp
    s_plane = cmds.nurbsPlane(
        name=prefix + "_stretchPlane",
        width=s_len,
        lengthRatio=0.2,
        patchesU=number_of_bones,
        axis=(0, 1, 0),
    )
    s_plane_shape = cmds.listRelatives(s_plane, shapes=True)[0]
    cmds.delete(cmds.parentConstraint(start_loc, end_loc, s_plane))
    # XXX: Is the orient constraint doing anything the parentConstraint isn't?
    cmds.delete(cmds.orientConstraint(start_loc, s_plane))
    cmds.delete(s_plane, constructionHistory=True)

    s_curve = cmds.curve(degree=1, point=[start_point, end_point])
    s_curve = cmds.rename(
        s_curve, prefix + "_stretchCurve"
    )  # If named at the creation time, the shape node doesn't get renamed

    plane_transform = s_plane[0]
    cmds.parent(start_loc, end_loc, plane_transform, s_curve, s_grp)

    # create wire deformer and dropoffLocator for twisting
    # XXX: Unpacking the results of creation makes it a lot easier to pass them around
    s_wire_transform, s_wire = cmds.wire(
        plane_transform, wire=s_curve, name=prefix + "_stretchWire"
    )
    cmds.wire(s_wire, edit=True, dropoffDistance=[(0, 20), (1, 20)])

    cmds.select(s_wire + ".u[0]", r=True)
    cmds.dropoffLocator(1.0, 1.0, s_wire_transform)
    cmds.select(s_wire + ".u[1]", r=True)
    cmds.dropoffLocator(1.0, 1.0, s_wire_transform)

    # skin wire to bone driver, connect rotation of locators to drop off locators twist
    # XXX: The method returns a single transform for the locator so we don't have
    # to access it with indexing
    cmds.connectAttr(
        start_loc + ".rotateX", s_wire_transform + ".wireLocatorTwist[0]"
    )
    cmds.connectAttr(end_loc + ".rotateX", s_wire_transform + ".wireLocatorTwist[1]")

    cmds.skinCluster(
        start_w_joint, end_w_joint, s_wire, maximumInfluences=1, toSelectedBones=True
    )

    # crating follicles on sPlane and joints
    s_joints_collection = []
    fol_grp = cmds.group(empty=True, name=prefix + "_follicleGrp")
    cmds.parent(fol_grp, s_grp)

    # XXX: If you don't want 0-based numbering, increase the start and end of
    # the range by 1 - saves having to modify the value each time in the loop
    for x in range(1, number_of_bones + 1):
        v_position = (1.0 / (number_of_bones + 1)) * x
        # XXX: This is a good example of where a function is useful. It's
        # important not to try and put everything into the function, just the
        # parts that might be re-usable for this or other tools.
        fol_trans, fol_shape = create_follicle(prefix, s_plane_shape, 0.5, v_position, num=x)
        # here I'm adding a joint, as the follicle is selected the joint is parented under it.
        # im also adding the joint to a list i can use later
        s_joints_collection.append(
            cmds.joint(name=prefix + "_stretchJoint_{:02d}".format(x))
        )
        cmds.parent(fol_trans, fol_grp)

    # creating nodes for stretching bones
    s_curve_shape = cmds.listRelatives(s_curve, shapes=True)[0]
    s_curve_info = cmds.createNode("curveInfo", name="SCurveInfo")
    # XXX: Deleted a call to rename() - as far as I could see, the createNode named it right
    cmds.connectAttr(s_curve_shape + ".worldSpace[0]", s_curve_info + ".inputCurve")

    joint_scale = cmds.createNode("multiplyDivide", name="sJointScale")
    cmds.setAttr(joint_scale + ".operation", 2)
    cmds.setAttr(joint_scale + ".input2X", s_len)
    cmds.connectAttr(s_curve_info + ".arcLength", joint_scale + ".input1X")

    # connecting up nodes to bones
    # XXX: Is there a reason the curve info and joint scale couldn't be created
    # before the follicles? If not, you could move it up there and then run
    # these connectAttr calls inside the "number_of_bones" loop and save looping
    # through it twice.
    for joint in s_joints_collection:
        cmds.connectAttr(joint_scale + ".outputX", joint + ".scaleX")

    # creating a variable for the base wire of the wire deformer
    s_base_wire = cmds.listConnections(
        s_wire_transform + ".baseWire", destination=False, source=True
    )[0]

    # creating group inorder to help organisation and prevent double transforms
    s_rig_grp = cmds.group(empty=True, name=prefix + "_stretchPlaneRigGrp")
    align(s_rig_grp, start_loc)

    cmds.parent(s_rig_grp, s_grp)
    cmds.parent(plane_transform, s_base_wire, start_loc, end_loc, s_rig_grp)
    cmds.setAttr(start_w_joint + ".visibility", False)
    cmds.setAttr(end_w_joint + ".visibility", False)

    # Connecting end locators to driving joints -will have to do this properly in the main script
    cmds.pointConstraint(end_joint, end_loc)
    cmds.connectAttr(
        end_joint + ".rotateZ", end_loc + ".rotateX"
    )  # TODO: add if statment for elbow/wrist rotations
    cmds.parent(start_joint, s_rig_grp)
    """
    for V0.2
    make squash nodes
    """
    # XXX: It's always good to return the most useful item(s) from a function.
    # I'm not sure what would be the most important here, so I'm just returning
    # the root group as an example
    return s_rig_grp


# XXX: When running a python script directly, it gets called "__main__". A common
# way for python to make a script executable directly is to check at the end of
# the file if the name is "__main__" and run code there. In a lot of cases,
# people will add a test use case here so they can easily run the script and see
# if it's working. It also makes it easy to see the usage at a glance.
if __name__ == '__main__':
    add_joint("Arm", "joint1")
