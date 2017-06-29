# Author-Patrick Rainsberry
# Description-Simplified Slicer for Fusion 360

# Importing sample Fusion Command
# Could import multiple Command definitions here
from .FusionSlicerLTCommand import FusionSlicerLTCommand

commands = []
command_definitions = []

# Define parameters for 1st command
cmd = {
    'cmd_name': 'Fusion Slicer LT',
    'cmd_description': 'Simplified Fusion Slicing App',
    'cmd_id': 'cmdID_slicer_lt',
    'cmd_resources': './resources',
    'workspace': 'FusionSolidEnvironment',
    'toolbar_panel_id': 'SolidScriptsAddinsPanel',
    'class': FusionSlicerLTCommand
}
command_definitions.append(cmd)



# Set to True to display various useful messages when debugging your app
debug = False


# Don't change anything below here:
for cmd_def in command_definitions:
    command = cmd_def['class'](cmd_def, debug)
    commands.append(command)


def run(context):
    for run_command in commands:
        run_command.on_run()


def stop(context):
    for stop_command in commands:
        stop_command.on_stop()
