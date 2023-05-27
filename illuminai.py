# Install Blender and required packages
!apt-get install -y blender
!pip install wheel
!pip install bpy==3.4

import json
import os
import random
from pathlib import Path
import numpy as np

import bpy
import pandas as pd

# Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')



# Save test_script.py
!echo "import bpy\nprint(bpy.context.scene.name)" > test_script.py

# Run Blender in background mode with the test script
!blender --background --python test_script.py

def extract_light_data():
    light_data = []
    for obj in bpy.context.scene.objects:
        if obj.type == 'LIGHT':
            light = {
                'name': obj.name,
                'type': obj.data.type,
                'location': list(obj.location),
                'rotation': list(obj.rotation_euler),
                'energy': obj.data.energy,
                'color': list(obj.data.color),
            }
            if obj.data.type == 'AREA':
                light['size'] = obj.data.size
            elif obj.data.type == 'SPOT':
                light['spot_size'] = obj.data.spot_size
                light['spot_blend'] = obj.data.spot_blend
            elif obj.data.type == 'SUN':
                light['size'] = None
            elif obj.data.type == 'POINT':
                light['size'] = None
            light_data.append(light)
        
    return light_data

def extract_object_data():
    object_data = []
    for obj in bpy.context.scene.objects:
        if obj.type in ['MESH', 'CURVE', 'SURFACE', 'META', 'FONT']:
            object_info = {
                'name': obj.name,
                'type': obj.type,
                'location': list(obj.location),
                'rotation': list(obj.rotation_euler),
                'dimensions': list(obj.dimensions),
                'bounding_box': [list(corner) for corner in obj.bound_box],
            }

            if obj.data.materials:
                material = obj.data.materials[0]
            else:
                material = bpy.data.materials.new(name="Default Material")
                material.use_nodes = True
                obj.data.materials.append(material)

            if material and material.use_nodes:
                principled_node = None
                for node in material.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        principled_node = node
                        break
                if not principled_node:
                    principled_node = material.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
                    material.node_tree.links.new(principled_node.outputs['BSDF'], material.node_tree.nodes['Material Output'].inputs['Surface'])

                base_color = principled_node.inputs['Base Color'].default_value[:3]
                object_info['base_color'] = list(base_color)

            object_data.append(object_info)

    return object_data

def extract_world_data():
    world = bpy.context.scene.world
    world_data = {
        'data_type': 'World',
        'background_color': list(world.color),
    }

    if world and world.use_nodes:
        node_tree = world.node_tree
        background_node = node_tree.nodes.get('Background')

        if background_node and background_node.inputs['Color'].is_linked:
            color_node = background_node.inputs['Color'].links[0].from_node
            if color_node.type == 'TEX_ENVIRONMENT':
                if not color_node.image:
                    sky_texture_node = node_tree.nodes.new('ShaderNodeTexSky')
                    sky_texture_node.location = color_node.location
                    sky_texture_node.turbidity = 1
                    node_tree.links.new(sky_texture_node.outputs['Color'], background_node.inputs['Color'])
                    node_tree.nodes.remove(color_node)
                else:
                    world_data['hdri_file'] = color_node.image.filepath

        if background_node:
            world_data['strength'] = background_node.inputs['Strength'].default_value

    return world_data

def extract_render_settings_data():
    scene = bpy.context.scene
    render_settings = {
        'render_engine': scene.render.engine,
        'file_name': bpy.data.filepath.split('/')[-1]  # name of the blend file
    }

    if scene.render.engine == 'CYCLES':
        render_settings['samples'] = scene.cycles.samples
    else:
        render_settings['samples'] = scene.eevee.taa_render_samples

    render_settings['use_ao'] = scene.eevee.use_gtao if scene.render.engine == 'BLENDER_EEVEE' else scene.world.light_settings.use_ambient_occlusion
    render_settings['ao_distance'] = scene.eevee.gtao_distance if scene.render.engine == 'BLENDER_EEVEE' else scene.world.light_settings.distance
    render_settings['ao_factor'] = scene.eevee.gtao_factor if scene.render.engine == 'BLENDER_EEVEE' else (scene.world.light_settings.energy if hasattr(scene.world.light_settings, 'energy') else 1.0)

    return render_settings

def calculate_distance(light_location, object_location):
    return np.sqrt((light_location[0] - object_location[0]) ** 2 +
                   (light_location[1] - object_location[1]) ** 2 +
                   (light_location[2] - object_location[2]) ** 2)

def save_data_to_file(data, output_file, blend_filename):
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            existing_data = json.load(f)
    else:
        existing_data = {}

    existing_data[blend_filename] = data

    with open(output_file, 'w') as f:
        json.dump(existing_data, f, indent=4)

def process_blend_file(blend_file):
    try:
        bpy.ops.wm.open_mainfile(filepath=str(blend_files_dir / blend_file))

        light_data = extract_light_data()
        object_data = extract_object_data()
        world_data = extract_world_data()
        render_settings_data = extract_render_settings_data()

        # Feature engineering code

        # Calculate distances between lights and objects
        for obj in object_data:
            for light in light_data:
                distance = calculate_distance(light['location'], obj['location'])
                obj[f'distance_to_{light["name"]}'] = distance

        # Split light color into individual channels
        for light in light_data:
            light['light_color_red'] = light['color'][0]
            light['light_color_green'] = light['color'][1]
            light['light_color_blue'] = light['color'][2]

        # Add a feature for the number of lights in the scene
        num_lights = len(light_data)
        for obj in object_data:
            obj['num_lights'] = num_lights

        # Additional feature engineering code

        output_data = {
            os.path.splitext(os.path.basename(blend_file))[0]: {
                'light_data': light_data,
                'object_data': object_data,
                'world_data': world_data,
                'render_settings_data': render_settings_data,
            }
        }
        print(f"Processed {blend_file}: {output_data}")
        return output_data
    except Exception as e:
        print(f"Error processing {blend_file}: {e}")
        return None

if __name__ == "__main__":
    def find_blend_files(directory):
        blend_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".blend"):
                    blend_files.append(os.path.join(root, file))
        return blend_files

    blend_files_dir = Path("/content/drive/MyDrive/Blender/BlenderData/")
    blend_files = find_blend_files(blend_files_dir)
    all_data = {}

    for blend_file in blend_files:
        output_data = process_blend_file(blend_file)
        if output_data is not None:
            all_data.update(output_data)

    output_file_path = blend_files_dir / "scene_data.json"
    with output_file_path.open("w") as json_file:
        json.dump(all_data, json_file, indent=4)

"""File Separation

**Light, Object, World, Camera, Render** Data in CSV

---
"""

import logging
import pandas as pd
from pathlib import Path

# Set up logging
logging.basicConfig(filename='blender_extraction.log', level=logging.INFO)

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, ', '.join(map(str, v))))
        else:
            items.append((new_key, v))
    return dict(items)

data_types = ['light_data', 'object_data', 'world_data', 'camera_data', 'render_settings_data']
file_count = len(all_data)

for data_type in data_types:
    data_frames = []
    for i, key in enumerate(all_data):
        logging.info(f'Processing file {i+1} of {file_count}: {key}')
        try:
            for item in all_data[key][data_type]:
                flat_item = flatten_dict(item)
                item_df = pd.DataFrame(flat_item, index=[0])
                item_df['blend_file'] = key
                data_frames.append(item_df)
        except KeyError:
            logging.warning(f"Key '{data_type}' not found for {key}")
        except Exception as e:
            logging.error(f"Error processing file {key}: {e}")

    if data_frames:
        df = pd.concat(data_frames, ignore_index=True)
        df.to_csv(Path('/content/drive/MyDrive/Blender/BlenderData', f'{data_type}.csv'), index=False)
        logging.info(f'Saved {data_type}.csv')
    else:
        logging.warning(f"No data frames to concatenate for {data_type}.")