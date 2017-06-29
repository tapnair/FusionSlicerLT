# ![](./resources/32x32.png) FusionSlicerLT

This is an [Autodesk Fusion 360](http://fusion360.autodesk.com/) script that's used for generating slices with custom notches

This sample is provided "As-is" with no guarantee of performance, reliability or warranty.

![Fusion Slicer LT](./resources/cover_image.png)


# Installation
[Click here to download the Add-in](https://github.com/tapnair/FusionSlicerLT/archive/master.zip)

After downloading the zip file follow the [installation instructions here](https://tapnair.github.io/installation.html) for your particular OS version of Fusion 360

## Usage
**The model must be oriented relative to the origin of the design.**
<br>The slices will be created in the X and Y directions
<br>The X direction slices will have the notch in the top of the section
<br>The Y direction slices will have the notches on the bottom of the section
<br>To change the orientation of the slices, simply rotate the model


1. Enter the Model environment
2. Select Addins/FusionSlicerLT
3. The target body is the body to be split.
4. Set the slice thickness
5. X Template and Y Template bodies are the bodies for use with custom "notching"
  <br>&nbsp;&nbsp;&nbsp; - The origin of the body will define the point on the slice where it is applied.
  <br>&nbsp;&nbsp;&nbsp; - By design the X Template is notched on the top and Y template is notch on the bottom
  <br>&nbsp;&nbsp;&nbsp; - X Template should be sketched on the Y-Z plane
  <br>&nbsp;&nbsp;&nbsp; - Y Template should be oriented on the X-Z Plane
6. Specify the spacing and quantity for each direction

![Command UI](./resources/readMe_Command.png)

![Command UI](./resources/readMe_Sketch.png)

![Command UI](./resources/readMe_Source_Body.png)

![Command UI](./resources/readMe_Template_Bodies.png)


## TODO
Add option for "non-custom" notches


## License
Samples are licensed under the terms of the [MIT License](http://opensource.org/licenses/MIT). Please see the [LICENSE](LICENSE) file for full details.

## Written by

Written by [Patrick Rainsberry](https://twitter.com/prrainsberry) <br /> (Autodesk Fusion 360 Business Development)

See more useful [Fusion 360 Utilities](https://tapnair.github.io/index.html)

[![Analytics](https://ga-beacon.appspot.com/UA-41076924-3/paramEdit)](https://github.com/igrigorik/ga-beacon)