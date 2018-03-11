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

SliceFace = namedtuple('SliceFace', ('face', 'body'))
SliceComponent = namedtuple('SliceComponent', ('occurrence', 'end_face'))


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

# Create slice in a given direction
def create_slices2(target_body, spacing, qty, base_plane, slice_thickness, name):
    target_comp = target_body.parentComponent

    # Feature Collections
    planes = target_comp.constructionPlanes

    component_slices = []
    face_slices = []

    for i in range(1, qty + 1):
        offset_value = adsk.core.ValueInput.createByReal(i * spacing)

        # Create construction plane input
        plane_input = planes.createInput()

        # Add construction plane by offset

        plane_input.setByOffset(base_plane, offset_value)
        plane = planes.add(plane_input)
        plane.name = name + '-' + str(i)

        slice_name = name + '-' + str(i)

        create_slice(plane, slice_thickness, target_body, face_slices, component_slices, slice_name)

    return component_slices, face_slices


def create_slice(plane: adsk.fusion.ConstructionPlane, slice_thickness: float, target_body: adsk.fusion.BRepBody,
                 face_slices, component_slices, slice_name):
    ao = get_app_objects()
    design = ao['design']

    target_comp = target_body.parentComponent

    new_occurrence = target_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    new_occurrence.activate()
    new_occurrence.component.name = slice_name

    # Feature Collections
    sketches = new_occurrence.component.sketches
    patches = new_occurrence.component.features.patchFeatures
    extrude_features = new_occurrence.component.features.extrudeFeatures

    # Create the sketch
    # todo fix plane creation
    mid_plane = plane
    mid_sketch = add_construction_sketch(sketches, mid_plane)
    mid_sketch.projectCutEdges(target_body)
    mid_sketch.name = 'Mid_Sketch'

    plus_plane = create_offset_plane(new_occurrence.component, slice_thickness / 2, plane)
    plus_plane.name = 'Plus_Plane'
    plus_sketch = add_construction_sketch(sketches, plus_plane)
    plus_sketch.projectCutEdges(target_body)
    plus_sketch.name = 'Plus_Sketch'

    minus_plane = create_offset_plane(new_occurrence.component, -slice_thickness / 2, plane)
    minus_plane.name = 'Minus_Plane'
    minus_sketch = add_construction_sketch(sketches, minus_plane)
    minus_sketch.projectCutEdges(target_body)
    minus_sketch.name = 'Minus_Sketch'

    mid_slices = []
    get_contained_profiles(mid_sketch, patches, target_body, True, mid_slices)

    plus_profiles = get_contained_profiles(plus_sketch, patches, target_body)
    minus_profiles = get_contained_profiles(minus_sketch, patches, target_body)

    thickness_value = adsk.core.ValueInput.createByReal(slice_thickness)
    negative_thickness_value = adsk.core.ValueInput.createByReal(-slice_thickness)

    if plus_profiles.count == 0:
        new_occurrence.component.name += '----FIX__ME'
        plus_sketch.name += '----FIX__ME'
        return
    plus_extrude = extrude_features.addSimple(plus_profiles, negative_thickness_value,
                                              adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    plus_bodies = []

    for body in plus_extrude.bodies:
        plus_bodies.append(body)

    create_face_slices(plus_extrude.endFaces, mid_slices, face_slices)

    # end_face = plus_extrude.endFaces[0]

    if minus_profiles.count == 0:
        new_occurrence.component.name += '----FIX__ME'
        minus_sketch.name += '----FIX__ME'
        return

    minus_extrude = extrude_features.addSimple(minus_profiles, thickness_value,
                                               adsk.fusion.FeatureOperations.IntersectFeatureOperation)

    # Get the current position of the timeline.
    start_position = design.timeline.markerPosition
    minus_extrude.timelineObject.rollTo(True)
    minus_extrude.participantBodies = plus_bodies
    design.timeline.markerPosition = start_position

    design.activateRootComponent()

    # slice_face = SliceFace()
    # slice_component = SliceComponent(new_occurrence, end_face)
    # moved_body = face.body.moveToComponent(new_occurrence)
    # moved_face = moved_body.faces.item(0)

    # SliceFace = namedtuple('SliceFace', ('face', 'body'))
    # SliceComponent = namedtuple('SliceComponent', ('occurrence', 'end_face'))
    # Todo build slices from list
    # Todo Build Slice components
    # Todo fix references

    # return SliceComponent(new_occurrence, end_face)

    # if not end_face.isValid:
    #     end_face = minus_extrude.endFaces[0]

    end_face = mid_slices[-1]
    component_slices.append(SliceComponent(new_occurrence, end_face))


def create_face_slices(extrude_faces, mid_faces, face_slices):
    extrude_bodies = []
    mid_bodies = []

    for e_face in extrude_faces:
        extrude_dict = {'body': e_face.body, 'area': e_face.evaluator.area, 'face': e_face}
        extrude_bodies.append(extrude_dict)

    for m_face in mid_faces:
        extrude_dict = {'body': m_face.body, 'area': m_face.evaluator.area, 'face': m_face}
        mid_bodies.append(extrude_dict)

        extrude_bodies = sorted(extrude_bodies, key=lambda k: k["area"])
        mid_bodies = sorted(mid_bodies, key=lambda k: k["area"])

    for i, mid_body in enumerate(mid_bodies):
        new_slice = SliceFace(mid_bodies[i]['face'], extrude_bodies[i]['body'])
        face_slices.append(new_slice)


def get_contained_profiles(sketch, patches, target_body, is_mid_plane=False, mid_slices=None):
    extrude_profiles = adsk.core.ObjectCollection.create()

    # Account for potential of multiple resulting faces in the slice
    for profile in sketch.profiles:

        # Create the patch feature
        patch_input = patches.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        patch_feature = patches.add(patch_input)

        # Possibly patch could create multiple faces, although unlikely in this application
        # for patch_face in patch_feature.faces:

        patch_face = patch_feature.faces[0]

        # Check if surface is actually in solid
        point = patch_face.pointOnFace
        containment = target_body.pointContainment(point)

        if containment == adsk.fusion.PointContainment.PointInsidePointContainment:
            extrude_profiles.add(profile)

            if is_mid_plane:
                mid_slices.append(patch_face)

            else:
                patch_feature.deleteMe()
        else:
            patch_feature.deleteMe()

    return extrude_profiles


def project_all_entities(sketch, entities):
    for entity in entities:
        sketch.project(entity)


# Create vertical lines at intersections of two face sets
# Post_Point = namedtuple('Post_Point', ('point', 'body', 'sketch_face', 'line', 'length'))
def make_posts(target_slices: List[SliceFace], intersect_slices: List[SliceFace]):
    top_points = []
    bottom_points = []

    for i, target_slice in enumerate(target_slices):
        sketches = target_slice.face.body.parentComponent.sketches
        post_sketch = add_construction_sketch(sketches, target_slice.face)

        for intersect_slice in intersect_slices:
            post_sketch.projectCutEdges(intersect_slice.face.body)

        lines = post_sketch.sketchCurves.sketchLines

        for line in lines:

            if not line.isConstruction:

                length = line.length
                start_point = line.startSketchPoint.worldGeometry
                end_point = line.endSketchPoint.worldGeometry

                if start_point.z > end_point.z:
                    top_points.append(Post_Point(start_point, target_slice.body, target_slice.face, line, length))
                    bottom_points.append(Post_Point(end_point, target_slice.body, target_slice.face, line, length))

                else:
                    top_points.append(Post_Point(end_point, target_slice.body, target_slice.face, line, length))
                    bottom_points.append(
                        Post_Point(start_point, target_slice.body, target_slice.face, line, length))

        post_sketch.name = 'Intersection Sketch-' + str(i)
        post_sketch.isVisible = False

    return top_points, bottom_points


def make_slots(target_body: adsk.fusion.BRepBody, post_points: List[Post_Point], thickness: float,
               direction: adsk.core.Vector3D):
    root_comp = target_body.parentComponent

    # Get extrude features
    # extrudes = root_comp.features.extrudeFeatures

    # Create sketch
    # sketches = root_comp.sketches

    for i, post_point in enumerate(post_points):

        sketches = post_point.body.parentComponent.sketches
        extrudes = post_point.body.parentComponent.features.extrudeFeatures

        slot_sketch = add_construction_sketch(sketches, post_point.sketch_face)

        sketch_lines = slot_sketch.sketchCurves.sketchLines

        center_point = slot_sketch.modelToSketchSpace(post_point.point)
        center_point.z = 0

        x_vector = direction.copy()
        x_vector.scaleBy(thickness / 2)

        y_vector = adsk.core.Vector3D.create(0, 0, 1)
        y_vector.scaleBy(post_point.length / 2)
        # trans_vector = adsk.core.Vector3D.create(post_point.length / 2, thickness / 2, 0)

        corner_point = post_point.point.copy()
        corner_point.translateBy(x_vector)
        corner_point.translateBy(y_vector)

        corner_point_sketch = slot_sketch.modelToSketchSpace(corner_point)
        corner_point_sketch.z = 0

        # corner_point.translateBy(adsk.core.Vector3D.create(post_point.length/2, thickness/2, 0))
        # corner_point_sketch = sketch_points.add(corner_point)

        rectangle_list = sketch_lines.addCenterPointRectangle(center_point, corner_point_sketch)

        # Get the profile defined by the rectangle
        prof = slot_sketch.profiles.item(0)

        thickness_value = adsk.core.ValueInput.createByReal(thickness)

        is_full_length = True
        extrude_input = extrudes.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
        extrude_input.setSymmetricExtent(thickness_value, is_full_length)

        # ao = get_app_objects()
        # ao['ui'].messageBox(post_point.body.objectType)
        extrude_input.participantBodies = [post_point.body]

        # Create the extrusion
        extrude = extrudes.add(extrude_input)

        slot_sketch.name = 'slot_sketch-' + str(i)
        slot_sketch.isVisible = False


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
def components_from_bodies(slice_results: List[SliceFace]):
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
def arrange_components(component_slices: List[SliceComponent], plane, spacing, direction_vector):

    # app = adsk.core.Application.get()
    # ui = app.userInterface
    # product = app.activeProduct
    # design = adsk.fusion.Design.cast(product)

    # Get Placement Direction from Edge

    # direction_vector = get_positive_unit_vector_from_edge(edge)

    # Get extents of stock in placement direction
    delta_plane = get_bounding_box_extent_in_direction(plane, direction_vector)

    # Set initial magnitude
    magnitude = 0.0
    magnitude -= delta_plane / 2

    # Iterate and place components
    for slice_component in component_slices:

        # Get extents of current component in placement direction
        delta = get_bounding_box_extent_in_direction(slice_component.occurrence, direction_vector)

        # ui.messageBox(str(delta))

        # Increment magnitude
        magnitude += spacing

        magnitude += delta / 2

        # Move component in specified direction by half its width
        transform_along_vector(slice_component.occurrence, direction_vector, magnitude)

        # Increment spacing value for next component
        magnitude += delta / 2


class StockSheet:
    def __init__(self, target_body: adsk.fusion.BRepBody, thickness):
        target_comp = get_app_objects()['root_comp']

        new_occurrence = target_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        new_occurrence.activate()

        # Feature Collections
        sketches = new_occurrence.component.sketches
        extrude_features = new_occurrence.component.features.extrudeFeatures

        sketch = sketches.add(new_occurrence.component.xYConstructionPlane)

        sketch.sketchCurves.sketchLines.addTwoPointRectangle(sketch.originPoint.geometry,
                                                             adsk.core.Point3D.create(100, 100, 0))

        # Get the profile defined by the rectangle
        profile = sketch.profiles.item(0)

        thickness_value = adsk.core.ValueInput.createByReal(thickness)

        # Create the extrusion
        extrude = extrude_features.addSimple(profile, thickness_value,
                                             adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        self.body = extrude.bodies[0]

        self.new_component = extrude.parentComponent

        self.occurrence = new_occurrence

        self.end_face = extrude.endFaces[0]
        # self.end_face = extrude.endFaces[0].createForAssemblyContext(self.occurrence)

        # adsk.fusion.Occurrence.cast(target_body).isGrounded = True

        get_app_objects()['design'].activateRootComponent()

        new_occurrence.isGrounded = True
        new_occurrence.isLightBulbOn = False


def create_offset_plane(target_comp, distance, base_plane):
    planes = target_comp.constructionPlanes

    # Add construction plane by offset
    plane_input = planes.createInput()

    offset_value = adsk.core.ValueInput.createByReal(distance)

    plane_input.setByOffset(base_plane, offset_value)

    return planes.add(plane_input)


class SlicerDef:
    def __init__(self, target_body=None, num_x=None, num_y=None, thickness=None, lay_this_flat=None):
        if target_body is not None:
            bounding_box = target_body.boundingBox

            target_comp = target_body.parentComponent

            self.target_body = target_body

            self.target_body = target_body
            self.x_plane = create_offset_plane(target_comp, bounding_box.minPoint.x, target_comp.yZConstructionPlane)
            self.x_plane.name = 'X_Zero_Plane'
            self.x_plane.isLightBulbOn = False

            self.y_plane = create_offset_plane(target_comp, bounding_box.minPoint.y, target_comp.xZConstructionPlane)
            self.y_plane.name = 'Y_Zero_Plane'
            self.y_plane.isLightBulbOn = False

            self.x_spacing = (bounding_box.maxPoint.x - bounding_box.minPoint.x) / (num_x + 1)
            self.y_spacing = (bounding_box.maxPoint.y - bounding_box.minPoint.y) / (num_y + 1)

            self.x_component_slices = []
            self.y_component_slices = []

            self.thickness = thickness

            if lay_this_flat:
                self.stock_sheet = StockSheet(target_body, thickness)
            else:
                self.stock_sheet = None

def lay_flat(component_slices: List[SliceComponent], stock_sheet: StockSheet):

    # Get the root component of the active design
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    root_comp = design.rootComponent

    key_type = adsk.fusion.JointKeyPointTypes.CenterKeyPoint

    # Apply Joints
    for slice_component in component_slices:

        face1 = slice_component.end_face
        face2 = stock_sheet.end_face

        # ui = app.userInterface
        # ui.messageBox(face1.objectType)
        # ui.messageBox(face1.body.parentComponent.name)
        # ui.messageBox(face2.objectType)
        # ui.messageBox(face2.body.parentComponent.name)

        # Create the joint geometry
        geo0 = adsk.fusion.JointGeometry.createByPlanarFace(face1, None, key_type)
        geo1 = adsk.fusion.JointGeometry.createByPlanarFace(face2, None, key_type)

        # Create joint input
        joints = root_comp.joints
        joint_input = joints.createInput(geo0, geo1)
        joint_input.setAsPlanarJointMotion(adsk.fusion.JointDirections.ZAxisJointDirection)

        # Create the joint
        joint = joints.add(joint_input)

        # joint.deleteMe()


# Lite version of Fusion 360 Slicer
class FusionSlicerLTCommand(Fusion360CommandBase):
    # Run whenever a user makes any change to a value or selection in the addin UI
    # Commands in here will be run through the Fusion processor and changes will be reflected in  Fusion graphics area
    def on_preview(self, command, inputs, args, input_values):
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

        SLICERDEF = SlicerDef(target_body, input_values['x_qty'], input_values['y_qty'],
                              input_values['slice_thickness'], input_values['lay_flat'])

        # Make X Slices
        x_component_slices, x_face_slices = create_slices2(target_body, SLICERDEF.x_spacing, input_values['x_qty'],
                                                           SLICERDEF.x_plane, input_values['slice_thickness'],
                                                           'X_Slice')

        # Make Y Slices
        y_component_slices, y_face_slices = create_slices2(target_body, SLICERDEF.y_spacing, input_values['y_qty'],
                                                           SLICERDEF.y_plane, input_values['slice_thickness'],
                                                           'Y_Slice')

        custom_slots = False

        if custom_slots:

            top_points, bottom_points = make_posts(x_face_slices, y_face_slices)
            make_custom_slots(target_body, top_points, input_values['x_template'])

            top_points, bottom_points = make_posts(y_face_slices, x_face_slices)
            make_custom_slots(target_body, bottom_points, input_values['y_template'])

        else:
            top_points, bottom_points = make_posts(x_face_slices, y_face_slices)
            make_slots(target_body, top_points, input_values['slice_thickness'],
                       target_body.parentComponent.yConstructionAxis.geometry.direction)

            top_points, bottom_points = make_posts(y_face_slices, x_face_slices)
            make_slots(target_body, bottom_points, input_values['slice_thickness'],
                       target_body.parentComponent.xConstructionAxis.geometry.direction)

        # Make Components

        # SLICERDEF.x_results = components_from_bodies(x_slices)
        # SLICERDEF.y_results = components_from_bodies(x_slices)

        SLICERDEF.x_component_slices = x_component_slices

        SLICERDEF.y_component_slices = y_component_slices

        # Todo needs to be a new command.  Need to do it with tagging

        # End Feature Group
        futil.end_group(start_index)

    def on_destroy(self, command, inputs, reason, input_values):

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

        # TODO definitely the problem occurs only when there are joints.
        # Option may be to move only, no joint.
        # Other option may be to delete joints before creating snapshot, althought it doesn't seem to work from API.


        # app = adsk.core.Application.get()
        # product = app.activeProduct
        # design = adsk.fusion.Design.cast(product)
        #
        # root_comp = design.rootComponent
        #
        # joints = root_comp.joints
        #
        # for joint in joints:
        #     joint.deleteMe()

        lay_flat(SLICERDEF.x_component_slices, SLICERDEF.stock_sheet)
        lay_flat(SLICERDEF.y_component_slices, SLICERDEF.stock_sheet)

        direction_vector = adsk.core.Vector3D.create(1, 0, 0)
        arrange_components(SLICERDEF.x_component_slices, SLICERDEF.stock_sheet.end_face, 1.0, direction_vector)

        direction_vector = adsk.core.Vector3D.create(0, 1, 0)
        arrange_components(SLICERDEF.y_component_slices, SLICERDEF.stock_sheet.end_face, 1.0, direction_vector)


        # design.snapshots.add()
