import adsk
import adsk.core
import adsk.fusion
import traceback

from .Fusion360Utilities.Fusion360Utilities import get_app_objects
from .Fusion360Utilities.Fusion360CommandBase import Fusion360CommandBase
from .Fusion360Utilities import Fusion360Utilities as futil


# Should move to utilities
def add_construction_sketch(sketches, plane):
    sketch = sketches.add(plane)

    for curve in sketch.sketchCurves:
        curve.isConstruction = True

    return sketch


# TODO Master list
# Identify which module each piece is in after dove tails.
# Show identification? Sketch on the model once its flat.
# For Dove Tails model flush "body split"


# Main Slice function
def make_slices(target_body, spacing, qty, base_plane, slice_thickness):
    target_comp = target_body.parentComponent

    # Feature Collections
    planes = target_comp.constructionPlanes
    sketches = target_comp.sketches
    thk_feats = target_comp.features.thickenFeatures

    slice_results = []

    slice_thickness /= 2

    for i in range(qty):

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
            surfaces_collection = adsk.core.ObjectCollection.create()

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

                    # If so, create thicken feature
                    surfaces_collection.add(face)

                    # Debug
                    # ao = get_app_objects()
                    # ao['ui'].messageBox("slice_thickness: " + str(slice_thickness))

                    thickness = adsk.core.ValueInput.createByReal((slice_thickness/2))

                    thicken_input = thk_feats.createInput(surfaces_collection, thickness, True,
                                                          adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
                    thk_feature = thk_feats.add(thicken_input)
                    new_body = thk_feature.bodies[0]

                    # TODO want to get a point on one face to find the face - probably should add some error checking here

                    ret = face.evaluator.getNormalAtPoint(face.pointOnFace)
                    direction = ret[1]

                    # Not currently working or used
                    end_face = find_end_face(thk_feature, direction)

                    slice_results.append((face, new_body, end_face))

                # Is the patch actually in a hole or void?  Delete
                else:
                    patch_feature.deleteMe()

    # TODO delete patch body?
    return slice_results


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
def make_posts(sketch_faces, intersect_faces, target_body):
    # Feature Collections
    target_comp = target_body.parentComponent
    sketches = target_comp.sketches

    top_points = []
    bottom_points = []

    for s_face in sketch_faces:
        sketch = add_construction_sketch(sketches, s_face[0])

        for i_face in intersect_faces:
            sketch.projectCutEdges(i_face[0].body)

        lines = sketch.sketchCurves.sketchLines

        for line in lines:

            if not line.isConstruction:
                start_point = line.startSketchPoint.worldGeometry
                end_point = line.endSketchPoint.worldGeometry

                if start_point.z > end_point.z:
                    top_points.append([start_point, s_face[1]])
                    bottom_points.append([end_point, s_face[1]])

                else:
                    top_points.append([end_point, s_face[1]])
                    bottom_points.append([start_point, s_face[1]])

    return top_points, bottom_points


# Make slots from template body
def make_slots(target_body, points, template_bodies):
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
def components_from_bodies(slice_results):
    component_results = []

    for slice_result in slice_results:
        original_body = slice_result[1]
        copied_body = original_body.copyToComponent(original_body.parentComponent)
        output_body = original_body.createComponent()

        # TODO move mid face to component

        component_result = {
            'output_body': output_body,
            'copied_body': copied_body,
            'mid_face': slice_result[0],
            'end_face': slice_result[2]

        }

        component_results.append(component_result)

    return component_results


# TODO create dovetails - Idea create sketch on the fly.
# TODO Create dummy surfaces with bounding box of target
# TODO Pattern at dove tails increment.  Create intersections to get top/bottom points with existing method
# TODO draw dove tails in place between top/bottom points
# TODO Might want to specify "start plane" for dove tail to begin then every so often

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
        # Get a reference to all relevant application objects in a dictionary
        app_objects = get_app_objects()
        ui = app_objects['ui']

        # Get the target body
        target_body = input_values['target_input'][0]

        # Start Feature group
        start_index = futil.start_group()

        # Make X Slices
        x_result = make_slices(target_body, input_values['x_spacing'], input_values['x_qty'],
                               target_body.parentComponent.yZConstructionPlane, input_values['slice_thickness'])

        # Make Y Slices
        y_result = make_slices(target_body, input_values['y_spacing'], input_values['y_qty'],
                               target_body.parentComponent.xZConstructionPlane, input_values['slice_thickness'])

        top_points, bottom_points = make_posts(x_result, y_result, target_body)
        make_slots(target_body, top_points, input_values['x_template'])

        top_points, bottom_points = make_posts(y_result, x_result, target_body)
        make_slots(target_body, bottom_points, input_values['y_template'])

        # Make Components
        x_component_results = components_from_bodies(x_result)
        y_component_results = components_from_bodies(y_result)

        # End Feature Group
        futil.end_group(start_index)

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

        command_inputs.addValueInput('x_spacing', 'X Spacing Distance', 'in', default_value)
        command_inputs.addIntegerSpinnerCommandInput('x_qty', 'X Quantity', 0, 1000, 1, 3)
        body_select = command_inputs.addSelectionInput('x_template', 'Select X Template Body', 'Select Body')
        body_select.addSelectionFilter('SolidBodies')
        body_select.setSelectionLimits(1, 1)

        command_inputs.addValueInput('y_spacing', 'Y Spacing Distance', 'in', default_value)
        command_inputs.addIntegerSpinnerCommandInput('y_qty', 'Y Quantity', 0, 1000, 1, 3)
        body_select = command_inputs.addSelectionInput('y_template', 'Select Y Template Body', 'Select Body')
        body_select.addSelectionFilter('SolidBodies')
        body_select.setSelectionLimits(1, 1)