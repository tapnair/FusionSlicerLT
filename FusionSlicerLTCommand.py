import adsk
import adsk.core
import adsk.fusion
import traceback

from collections import defaultdict, namedtuple
from typing import List

from .Fusion360Utilities.Fusion360Utilities import get_app_objects
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities import Fusion360Utilities as futil

Post = namedtuple('Post', ('top_point', 'bottom_point', 'line', 'length'))

Post_Point = namedtuple('Post_Point', ('point', 'body', 'sketch_face', 'line', 'length'))

Slice = namedtuple('Slice', ('face', 'new_body', 'end_face', 'occurrence'))


# Should move to utilities
def add_construction_sketch(sketches, plane):
    sketch = sketches.add(plane)

    for curve in sketch.sketchCurves:
        curve.isConstruction = True

    return sketch

SLICERDEF = None

# TODO Master list
# Identify which module each piece is in after dove tails.
# Show identification? Sketch on the model once its flat.
# For Dove Tails model flush "body split"


# Main Slice function
def create_slices(target_body, spacing, qty, base_plane, slice_thickness):
    target_comp = target_body.parentComponent

    # Feature Collections
    planes = target_comp.constructionPlanes
    sketches = target_comp.sketches

    slice_results = []

    for i in range(1, qty+1):

        # Create construction plane input
        plane_input = planes.createInput()

        # Add construction plane by offset
        offset_value = adsk.core.ValueInput.createByReal(i * spacing)
        plane_input.setByOffset(base_plane, offset_value)
        plane = planes.add(plane_input)

        # Create the sketch
        sketch = add_construction_sketch(sketches, plane)
        sketch.projectCutEdges(target_body)

        # Account for potential of multiple resulting faces in the slice
        for profile in sketch.profiles:

            # Create the patch feature
            patches = target_comp.features.patchFeatures
            patch_input = patches.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
            patch_feature = patches.add(patch_input)

            # Possibly patch could create multiple faces, although unlikely in this application
            for face in patch_feature.faces:

                # Check if surface is actually in solid
                point = face.pointOnFace
                containment = target_body.pointContainment(point)
                if containment == adsk.fusion.PointContainment.PointInsidePointContainment:

                    new_slice = extrude_face(face, slice_thickness, target_body)

                    # 'Slice', ('face', 'new_body', 'end_face')
                    slice_results.append(new_slice)

                # Is the patch actually in a hole or void?  Delete
                else:
                    patch_feature.deleteMe()

    # TODO delete patch body?
    return slice_results


def extrude_face(face: adsk.fusion.BRepFace, slice_thickness: float, target_body: adsk.fusion.BRepBody):

    ao = get_app_objects()
    design = ao['design']

    target_comp = target_body.parentComponent

    # Feature Collections
    sketches = target_comp.sketches

    patches = target_comp.features.patchFeatures

    # Create the sketch
    plus_plane = create_offset_plane(target_comp, slice_thickness / 2, face)
    plus_sketch = add_construction_sketch(sketches, plus_plane)
    plus_sketch.projectCutEdges(target_body)

    minus_plane = create_offset_plane(target_comp, -slice_thickness / 2, face)
    minus_sketch = add_construction_sketch(sketches, minus_plane)
    minus_sketch.projectCutEdges(target_body)

    # mid_sketch = add_construction_sketch(sketches, face)
    #
    # project_all_entities(mid_sketch, plus_sketch.sketchCurves)
    # project_all_entities(mid_sketch, minus_sketch.sketchCurves)

    plus_profiles = get_contained_profiles(plus_sketch, patches, target_body)
    minus_profiles = get_contained_profiles(minus_sketch, patches, target_body)

    thickness_value = adsk.core.ValueInput.createByReal(slice_thickness)
    negative_thickness_value = adsk.core.ValueInput.createByReal(-slice_thickness)

    # extrude_input = extrude_features.createInput(plus_profiles, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    # extrude_input.setOneSideExtent(thickness_value, direction)

    new_occurrence = target_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())

    new_occurrence.activate()

    extrude_features = new_occurrence.component.features.extrudeFeatures

    plus_extrude = extrude_features.addSimple(plus_profiles, negative_thickness_value,
                                              adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    plus_bodies = []

    for body in plus_extrude.bodies:
        plus_bodies.append(body)

    end_face = plus_extrude.endFaces[0]

    minus_extrude = extrude_features.addSimple(minus_profiles, thickness_value,
                                               adsk.fusion.FeatureOperations.IntersectFeatureOperation)

    # Get the current position of the timeline.
    start_position = design.timeline.markerPosition

    # Roll back the time line to the joint.
    minus_extrude.timelineObject.rollTo(True)

    minus_extrude.participantBodies = plus_bodies

    # Move the marker back
    design.timeline.markerPosition = start_position

    design.activateRootComponent()

    moved_body = face.body.moveToComponent(new_occurrence)

    moved_face = moved_body.faces.item(0)

    if minus_extrude.bodies.count > 0:

        new_body = plus_extrude.bodies[0]
        end_face = plus_extrude.endFaces[0]
        return Slice(moved_face, new_body, end_face, new_occurrence)

    else:
        return Slice(moved_face, new_occurrence.component.bRepBodies.item(0), end_face, new_occurrence)


def get_contained_profiles(sketch, patches, target_body):

    extrude_profiles = adsk.core.ObjectCollection.create()

    # Account for potential of multiple resulting faces in the slice
    for profile in sketch.profiles:

        # Create the patch feature
        patch_input = patches.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        patch_feature = patches.add(patch_input)

        # Possibly patch could create multiple faces, although unlikely in this application
        for patch_face in patch_feature.faces:

            # Check if surface is actually in solid
            point = patch_face.pointOnFace
            containment = target_body.pointContainment(point)

            if containment == adsk.fusion.PointContainment.PointInsidePointContainment:
                extrude_profiles.add(profile)

        patch_feature.deleteMe()

    return extrude_profiles


def project_all_entities(sketch, entities):
    for entity in entities:
        sketch.project(entity)


# Old method of creating slice with a thicken feature
def thicken_face(face, slice_thickness, thk_feats):
    surfaces_collection = adsk.core.ObjectCollection.create()

    # If so, create thicken feature
    surfaces_collection.add(face)

    # Debug
    # ao = get_app_objects()
    # ao['ui'].messageBox("slice_thickness: " + str(slice_thickness))

    thickness = adsk.core.ValueInput.createByReal((slice_thickness / 2))

    thicken_input = thk_feats.createInput(surfaces_collection, thickness, True,
                                          adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    thk_feature = thk_feats.add(thicken_input)
    new_body = thk_feature.bodies[0]

    # TODO want to get a point on one face to find the face - probably should add some error checking here

    ret = face.evaluator.getNormalAtPoint(face.pointOnFace)
    direction = ret[1]

    # Not currently working or used
    end_face = find_end_face(thk_feature, direction)

    return Slice(face, new_body, end_face)


# Find the end face of a feature
def find_end_face(feature, direction):
    tolerance = .01
    for face in feature.faces:

        ret = face.evaluator.getNormalAtPoint(face.pointOnFace)
        normal = ret[1]
        if normal.angleTo(direction) <= tolerance:
            end_face = face

    return end_face


# Create vertical lines at intersections of two face sets
def make_posts(target_slices: List[Slice], intersect_slices: List[Slice], target_body: adsk.fusion.BRepBody):
    target_comp = target_body.parentComponent



    top_points = []
    bottom_points = []

    for target_slice in target_slices:
        sketches = target_slice.face.body.parentComponent.sketches
        sketch = add_construction_sketch(sketches, target_slice.face)

        for i_face in intersect_slices:
            sketch.projectCutEdges(i_face[0].body)

        lines = sketch.sketchCurves.sketchLines

        for line in lines:

            length = line.length

            if not line.isConstruction:
                start_point = line.startSketchPoint.worldGeometry
                end_point = line.endSketchPoint.worldGeometry

                # 'Post_Point', ('point', 'body', 'sketch_face', 'line', 'length')
                if start_point.z > end_point.z:
                    top_points.append(Post_Point(start_point, target_slice.new_body, target_slice.face, line, length))
                    bottom_points.append(Post_Point(end_point, target_slice.new_body, target_slice.face, line, length))

                else:
                    top_points.append(Post_Point(end_point, target_slice.new_body, target_slice.face, line, length))
                    bottom_points.append(
                        Post_Point(start_point, target_slice.new_body, target_slice.face, line, length))

    return top_points, bottom_points


def make_slots(target_body: adsk.fusion.BRepBody, post_points: List[Post_Point], thickness: float,
               direction: adsk.core.Vector3D):
    root_comp = target_body.parentComponent

    # Get extrude features
    extrudes = root_comp.features.extrudeFeatures

    # Create sketch
    sketches = root_comp.sketches

    for post_point in post_points:
        sketch = add_construction_sketch(sketches, post_point.sketch_face)

        sketch_lines = sketch.sketchCurves.sketchLines
        sketch_points = sketch.sketchPoints

        # center_point = post_point.point
        center_point = sketch.modelToSketchSpace(post_point.point)
        center_point.z = 0

        # center_point_sketch = sketch_points.add(center_point)

        x_vector = direction.copy()
        x_vector.scaleBy(thickness / 2)

        y_vector = adsk.core.Vector3D.create(0, 0, 1)
        y_vector.scaleBy(post_point.length / 2)
        trans_vector = adsk.core.Vector3D.create(post_point.length / 2, thickness / 2, 0)

        corner_point = post_point.point.copy()
        corner_point.translateBy(x_vector)
        corner_point.translateBy(y_vector)

        corner_point_sketch = sketch.modelToSketchSpace(corner_point)
        corner_point_sketch.z = 0

        # corner_point.translateBy(adsk.core.Vector3D.create(post_point.length/2, thickness/2, 0))
        # corner_point_sketch = sketch_points.add(corner_point)

        rectangle_list = sketch_lines.addCenterPointRectangle(center_point, corner_point_sketch)

        # Get the profile defined by the rectangle
        prof = sketch.profiles.item(0)

        thickness_value = adsk.core.ValueInput.createByReal(thickness)

        is_full_length = True
        extrude_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
        extrude_input.setSymmetricExtent(thickness_value, is_full_length)

        # ao = get_app_objects()
        # ao['ui'].messageBox(post_point.body.objectType)
        extrude_input.participantBodies = [post_point.body]

        # Create the extrusion
        extrude = extrudes.add(extrude_input)


# Make slots from template body
def make_custom_slots(target_body, points, template_bodies):
    target_component = target_body.parentComponent

    move_feats = target_component.features.moveFeatures

    for point in points:

        translation_vector = adsk.core.Vector3D.create(point[0].x, point[0].y, point[0].z)

        if translation_vector.length > 0:
            new_collection = adsk.core.ObjectCollection.create()
            tool_bodies = []

            for body in template_bodies:
                new_body = body.copyToComponent(target_component)
                new_collection.add(new_body)
                tool_bodies.append(new_body)

            transform_matrix = adsk.core.Matrix3D.create()
            transform_matrix.translation = translation_vector

            move_input = move_feats.createInput(new_collection, transform_matrix)
            move_feats.add(move_input)

            futil.combine_feature(point[1], tool_bodies, adsk.fusion.FeatureOperations.CutFeatureOperation)


# Create components from all bodies
# Should add to utilities
def components_from_bodies(slice_results: List[Slice]):
    component_results = []

    for slice_result in slice_results:
        original_body = slice_result.new_body
        # copied_body = original_body.copyToComponent(original_body.parentComponent)
        output_body = original_body.createComponent()

        # TODO move mid face to component

        component_result = {
            'output_body': output_body,
            'output_component': output_body.parentComponent,
            # 'copied_body': copied_body,
            'mid_face': slice_result.face,
            'end_face': slice_result.end_face

        }

        component_results.append(component_result)

    return component_results


# Returns a normalized vector in positive XYZ space from a given edge
def get_positive_unit_vector_from_edge(edge):
    # Set up a vector based on input edge
    (returnValue, startPoint, endPoint) = edge.geometry.evaluator.getEndPoints()
    direction_vector = adsk.core.Vector3D.create(endPoint.x - startPoint.x,
                                                 endPoint.y - startPoint.y,
                                                 endPoint.z - startPoint.z)
    direction_vector.normalize()

    if direction_vector.x < 0:
        direction_vector.x *= -1
    if direction_vector.y < 0:
        direction_vector.y *= -1
    if direction_vector.z < 0:
        direction_vector.z *= -1

    return direction_vector


# Returns the magnatude of the bounding box in the specified direction
def get_bounding_box_extent_in_direction(component, direction_vector):
    max_point = component.boundingBox.maxPoint
    min_point = component.boundingBox.minPoint
    delta_vector = adsk.core.Vector3D.create(max_point.x - min_point.x,
                                             max_point.y - min_point.y,
                                             max_point.z - min_point.z)

    delta = delta_vector.dotProduct(direction_vector)
    return delta


# Transforms an occurance along a specified vector by a specified amount
def transform_along_vector(occurrence, directionVector, magnatude):
    # Create a vector for the translation
    vector = directionVector.copy()
    vector.scaleBy(magnatude)

    # Create a transform to do move
    transform = adsk.core.Matrix3D.cast(occurrence.transform)
    new_transform = adsk.core.Matrix3D.create()
    new_transform.translation = vector
    transform.transformBy(new_transform)

    # Transform Component
    occurrence.transform = transform


# Arranges components on a plane with a given spacing
def arrange_components(slice_results, plane, spacing, direction_vector):
    app = adsk.core.Application.get()
    #    ui = app.userInterface
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)

    # Get Placement Direction from Edge

    # direction_vector = get_positive_unit_vector_from_edge(edge)

    # Get extents of stock in placement direction
    delta_plane = get_bounding_box_extent_in_direction(plane, direction_vector)

    # Set initial magnitude
    magnitude = 0.0
    magnitude -= delta_plane / 2

    # Iterate and place components
    for slice_result in slice_results:

        # Get extents of current component in placement direction
        delta = get_bounding_box_extent_in_direction(slice_result.occurrence, direction_vector)

        app = adsk.core.Application.get()
        ui = app.userInterface
        ui.messageBox(str(delta))
        # Increment magnitude b
        # y desired component size and spacing
        magnitude += spacing
        magnitude += delta / 2

        # Move component in specified direction by half its width
        transform_along_vector(slice_result.occurrence, direction_vector, magnitude)

        # Increment spacing value for next component
        magnitude += delta / 2


class StockSheet:
    def __init__(self, target_body: adsk.fusion.BRepBody, thickness):
        target_comp = target_body.parentComponent

        # Feature Collections
        sketches = target_comp.sketches
        extrude_features = target_comp.features.extrudeFeatures

        sketch = sketches.add(target_comp.xYConstructionPlane)

        sketch.sketchCurves.sketchLines.addTwoPointRectangle(sketch.originPoint.geometry,
                                                             adsk.core.Point3D.create(100, 100, 0))

        # Get the profile defined by the rectangle
        profile = sketch.profiles.item(0)

        thickness_value = adsk.core.ValueInput.createByReal(thickness)

        # Create the extrusion
        extrude = extrude_features.addSimple(profile, thickness_value,
                                             adsk.fusion.FeatureOperations.NewComponentFeatureOperation)

        self.body = extrude.bodies[0]

        self.new_component = extrude.parentComponent

        self.occurrence = adsk.fusion.Occurrence.cast(target_body.parentComponent)

        self.end_face = extrude.endFaces[0]
        # self.end_face = extrude.endFaces[0].createForAssemblyContext(self.occurrence)

        # adsk.fusion.Occurrence.cast(target_body).isGrounded = True






def create_offset_plane(target_comp, distance, base_plane):
    planes = target_comp.constructionPlanes

    # Add construction plane by offset
    plane_input = planes.createInput()

    offset_value = adsk.core.ValueInput.createByReal(distance)

    plane_input.setByOffset(base_plane, offset_value)

    return planes.add(plane_input)


class SlicerDef:
    def __init__(self, target_body=None, num_x=None, num_y=None, thickness=None):

        if target_body is not None:
            bounding_box = target_body.boundingBox

            target_comp = target_body.parentComponent

            self.target_body = target_body

            self.target_body = target_body
            self.x_plane = create_offset_plane(target_comp, bounding_box.minPoint.x, target_comp.yZConstructionPlane)
            self.y_plane = create_offset_plane(target_comp, bounding_box.minPoint.y, target_comp.xZConstructionPlane)

            self.x_spacing = (bounding_box.maxPoint.x - bounding_box.minPoint.x) / (num_x + 1)
            self.y_spacing = (bounding_box.maxPoint.y - bounding_box.minPoint.y) / (num_y + 1)

            self.x_results = []
            self.y_results = []

            self.thickness = thickness

            self.stock_sheet = StockSheet(target_body, thickness)


def lay_flat(slice_components, stock_sheet):

    # Get the root component of the active design
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    root_comp = design.rootComponent

    # ui = app.userInterface
    # ui.messageBox(face1.objectType)
    # ui.messageBox(face1.body.parentComponent.name)
    # ui.messageBox(face2.objectType)
    # ui.messageBox(face2.body.parentComponent.name)

    key_type = adsk.fusion.JointKeyPointTypes.CenterKeyPoint

    # Apply Joints
    for slice_component in slice_components:

        face1 = slice_component.face
        face2 = stock_sheet.end_face

        # Create the joint geometry
        geo0 = adsk.fusion.JointGeometry.createByPlanarFace(face1, None, key_type)
        geo1 = adsk.fusion.JointGeometry.createByPlanarFace(face2, None, key_type)

        # Create joint input
        joints = root_comp.joints
        joint_input = joints.createInput(geo0, geo1)
        joint_input.setAsPlanarJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)

        # Create the joint
        joints.add(joint_input)


# Lite version of Fusion 360 Slicer
class FusionSlicerLTCommand(Fusion360CommandBase):
    # Run whenever a user makes any change to a value or selection in the addin UI
    # Commands in here will be run through the Fusion processor and changes will be reflected in  Fusion graphics area
    def on_preview(self, command, inputs, args, input_values):
        pass

    # Run after the command is finished.
    # Can be used to launch another command automatically or do other clean up.
    def on_destroy(self, command, inputs, reason, input_values):
        pass

    # Run when any input is changed.
    # Can be used to check a value and then update the add-in UI accordingly
    def on_input_changed(self, command_, command_inputs, changed_input, input_values):
        pass

    # Run when the user presses OK
    # This is typically where your main program logic would go
    def on_execute(self, command, inputs, args, input_values):

        global SLICERDEF

        # Get a reference to all relevant application objects in a dictionary
        app_objects = get_app_objects()
        ui = app_objects['ui']

        # Get the target body
        target_body = input_values['target_input'][0]

        # Start Feature group
        start_index = futil.start_group()

        SLICERDEF = SlicerDef(target_body, input_values['x_qty'], input_values['y_qty'], input_values['slice_thickness'])

        # Make X Slices
        x_slices = create_slices(target_body, SLICERDEF.x_spacing, input_values['x_qty'],
                                 SLICERDEF.x_plane, input_values['slice_thickness'])

        # Make Y Slices
        y_slices = create_slices(target_body, SLICERDEF.y_spacing, input_values['y_qty'],
                                 SLICERDEF.y_plane, input_values['slice_thickness'])

        custom_slots = False

        if custom_slots:

            top_points, bottom_points = make_posts(x_slices, y_slices, target_body)
            make_custom_slots(target_body, top_points, input_values['x_template'])

            top_points, bottom_points = make_posts(y_slices, x_slices, target_body)
            make_custom_slots(target_body, bottom_points, input_values['y_template'])

        else:
            top_points, bottom_points = make_posts(x_slices, y_slices, target_body)
            make_slots(target_body, top_points, input_values['slice_thickness'],
                       target_body.parentComponent.yConstructionAxis.geometry.direction)

            top_points, bottom_points = make_posts(y_slices, x_slices, target_body)
            make_slots(target_body, bottom_points, input_values['slice_thickness'],
                       target_body.parentComponent.xConstructionAxis.geometry.direction)

        # Make Components

        # SLICERDEF.x_results = components_from_bodies(x_slices)
        # SLICERDEF.y_results = components_from_bodies(x_slices)

        SLICERDEF.x_results = x_slices

        SLICERDEF.y_results = y_slices

        # Todo needs to be a new command.  Need to do it with tagging

        # End Feature Group
        futil.end_group(start_index)

        if input_values['lay_flat']:

            app_objects = get_app_objects()
            next_command = app_objects['ui'].commandDefinitions.itemById('cmdID_slicer_lt2')
            next_command.execute()

    # Run when the user selects your command icon from the Fusion 360 UI
    # Typically used to create and display a command dialog box
    # The following is a basic sample of a dialog UI
    def on_create(self, command, command_inputs):
        # Select the bodies
        body_select = command_inputs.addSelectionInput('target_input', 'Select Source Body', 'Select Body')
        body_select.addSelectionFilter('SolidBodies')
        body_select.setSelectionLimits(1, 1)

        # Create a default value using a string
        default_value = adsk.core.ValueInput.createByString('1.0 in')
        default_thk = adsk.core.ValueInput.createByString('.1 in')

        # Create a few inputs in the UI
        command_inputs.addValueInput('slice_thickness', 'Slice Thickness', 'in', default_thk)

        # command_inputs.addValueInput('x_spacing', 'X Spacing Distance', 'in', default_value)
        command_inputs.addIntegerSpinnerCommandInput('x_qty', 'X Quantity', 0, 1000, 1, 1)
        # body_select = command_inputs.addSelectionInput('x_template', 'Select X Template Body', 'Select Body')
        # body_select.addSelectionFilter('SolidBodies')
        # body_select.setSelectionLimits(1, 1)

        # command_inputs.addValueInput('y_spacing', 'Y Spacing Distance', 'in', default_value)
        command_inputs.addIntegerSpinnerCommandInput('y_qty', 'Y Quantity', 0, 1000, 1, 1)
        # body_select = command_inputs.addSelectionInput('y_template', 'Select Y Template Body', 'Select Body')
        # body_select.addSelectionFilter('SolidBodies')
        # body_select.setSelectionLimits(1, 1)

        command_inputs.addBoolValueInput('lay_flat', 'Lay Parts Flat?', True, '', False)

# Lite version of Fusion 360 Slicer
class FusionSlicerLTCommand2(Fusion360CommandBase):

    def on_execute(self, command, inputs, args, input_values):
        global SLICERDEF

        lay_flat(SLICERDEF.target_body, SLICERDEF.x_results, 1.0, SLICERDEF.thickness, SLICERDEF.stock_sheet, direction_vector)
        lay_flat(SLICERDEF.target_body, SLICERDEF.y_results, 1.0, SLICERDEF.thickness, SLICERDEF.stock_sheet, direction_vector)

        direction_vector = adsk.core.Vector3D.create(1, 0, 0)
        arrange_components(SLICERDEF.x_results, SLICERDEF.stock_sheet.end_face, 1.0, direction_vector)

        direction_vector = adsk.core.Vector3D.create(0, 1, 0)
        arrange_components(SLICERDEF.y_results, SLICERDEF.stock_sheet.end_face, 1.0, direction_vector)