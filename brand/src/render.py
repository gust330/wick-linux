"""Renders the light behind the Wick icon with Cycles.
Run: Blender -b -P brand/src/render.py -- <out dir> <samples>

Writes glow.png for the icon, and coal.png, the same light without the ember's halo, for wider layouts.

Two emitters on one wall: a coal below the frame, and the halo of the ember. Doing this in a renderer rather
than as a gradient gives real falloff and dithered 16-bit output, so the dark end of the ramp does not band.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
SAMPLES = int(argv[1]) if len(argv) > 1 else 128
SIZE = 1024
ORTHO = 12.0

# The ember's centre from brand/logo/mark-mono.svg, on its 24-unit grid, placed as the icon places the mark.
MARK_SCALE = 0.74
EMBER_GRID = (15.8, 11.9)
EMBER = (
    (EMBER_GRID[0] - 12) * MARK_SCALE * ORTHO / 24,
    (12 - EMBER_GRID[1]) * MARK_SCALE * ORTHO / 24,
)


def srgb(hex_value):
    def linear(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (linear(hex_value >> 16 & 255), linear(hex_value >> 8 & 255), linear(hex_value & 255), 1)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = False
scene.render.resolution_x = SIZE
scene.render.resolution_y = SIZE
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "16"
scene.render.dither_intensity = 1.0
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"

camera = bpy.data.cameras.new("camera")
camera.type = "ORTHO"
camera.ortho_scale = ORTHO
camera_object = bpy.data.objects.new("camera", camera)
camera_object.location = (0, 0, 20)
scene.collection.objects.link(camera_object)
scene.camera = camera_object

material = bpy.data.materials.new("light")
material.use_nodes = True
nodes = material.node_tree.nodes
links = material.node_tree.links
nodes.clear()


def new(kind, **inputs):
    node = nodes.new(kind)
    for key, value in inputs.items():
        node.inputs[key.replace("_", " ")].default_value = value
    return node


output = new("ShaderNodeOutputMaterial")
coords = new("ShaderNodeTexCoord")

# The coal: wide and low, warped by noise so it reads as heat and not as a CSS radial-gradient.
squash = new("ShaderNodeMapping", Scale=(0.60, 1.0, 1.0))
links.new(coords.outputs["Object"], squash.inputs["Vector"])
noise = new("ShaderNodeTexNoise", Scale=0.34, Detail=3.0, Roughness=0.45)
links.new(coords.outputs["Object"], noise.inputs["Vector"])
centred = nodes.new("ShaderNodeVectorMath")
centred.operation = "SUBTRACT"
centred.inputs[1].default_value = (0.5, 0.5, 0.5)
links.new(noise.outputs["Color"], centred.inputs[0])
amount = nodes.new("ShaderNodeVectorMath")
amount.operation = "SCALE"
amount.inputs["Scale"].default_value = 1.3
links.new(centred.outputs["Vector"], amount.inputs[0])
warped = nodes.new("ShaderNodeVectorMath")
warped.operation = "ADD"
links.new(squash.outputs["Vector"], warped.inputs[0])
links.new(amount.outputs["Vector"], warped.inputs[1])
distance = nodes.new("ShaderNodeVectorMath")
distance.operation = "DISTANCE"
distance.inputs[1].default_value = (0, -8.7, 0)
links.new(warped.outputs["Vector"], distance.inputs[0])
normalised = nodes.new("ShaderNodeMath")
normalised.operation = "DIVIDE"
normalised.inputs[1].default_value = 11.0
links.new(distance.outputs["Value"], normalised.inputs[0])

ramp = nodes.new("ShaderNodeValToRGB")
stops = [
    (0.00, 0xFFD9A0),
    (0.20, 0xFF9A50),
    (0.34, 0xEC5E26),
    (0.50, 0xA42C14),
    (0.68, 0x3C1410),
    (0.88, 0x130D0C),
    (1.00, 0x0B0909),
]
ramp.color_ramp.interpolation = "EASE"
while len(ramp.color_ramp.elements) < len(stops):
    ramp.color_ramp.elements.new(0.5)
for element, (position, color) in zip(ramp.color_ramp.elements, stops):
    element.position = position
    element.color = srgb(color)
links.new(normalised.outputs["Value"], ramp.inputs["Fac"])

# The ember's halo: inverse-square-ish falloff around its position, added on top.
to_ember = nodes.new("ShaderNodeVectorMath")
to_ember.operation = "DISTANCE"
to_ember.inputs[1].default_value = (EMBER[0], EMBER[1], 0)
links.new(coords.outputs["Object"], to_ember.inputs[0])
square = nodes.new("ShaderNodeMath")
square.operation = "POWER"
square.inputs[1].default_value = 2.0
links.new(to_ember.outputs["Value"], square.inputs[0])
falloff = nodes.new("ShaderNodeMath")
falloff.operation = "DIVIDE"
falloff.inputs[0].default_value = 0.16
HALO = falloff.inputs[0]
links.new(square.outputs["Value"], falloff.inputs[1])
softened = nodes.new("ShaderNodeMath")
softened.operation = "ADD"
softened.inputs[1].default_value = 0.42
links.new(square.outputs["Value"], softened.inputs[0])
links.new(softened.outputs["Value"], falloff.inputs[1])

tint = nodes.new("ShaderNodeVectorMath")
tint.operation = "SCALE"
tint.inputs[0].default_value = srgb(0xFF7A2E)[:3]
links.new(falloff.outputs["Value"], tint.inputs["Scale"])

total = nodes.new("ShaderNodeVectorMath")
total.operation = "ADD"
links.new(ramp.outputs["Color"], total.inputs[0])
links.new(tint.outputs["Vector"], total.inputs[1])

emission = nodes.new("ShaderNodeEmission")
links.new(total.outputs["Vector"], emission.inputs["Color"])
links.new(emission.outputs[0], output.inputs["Surface"])

bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
bpy.context.object.data.materials.append(material)

scene.render.filepath = os.path.join(OUT, "glow.png")
bpy.ops.render.render(write_still=True)

HALO.default_value = 0
scene.render.resolution_x = 2400
scene.render.resolution_y = 1350
camera.sensor_fit = "VERTICAL"
scene.render.filepath = os.path.join(OUT, "coal.png")
bpy.ops.render.render(write_still=True)
