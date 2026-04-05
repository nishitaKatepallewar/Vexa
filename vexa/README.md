# Vexa (v0.1)

QC checks in seconds.

## Architecture

![System Architecture](assets/architecture_v0.1.png)

1. Select object(s) and type a prompt in Blender's N-Panel
2. Prompt + available functions sent to LLM as JSON schema
3. LLM returns structured function call
4. Vexa executes the function in Blender
5. Result displayed in panel

AI interpretation remains separate from Blender operations.

## What works:

- Maps natural language to function calls ("how many verts" → `count_vertices()`) 
- Fuzzy matching handles minor output variations
- Zero external dependencies, runs natively in Blender

## What doesn't:

- Hardcoded for Gemini API (switching LLMs requires rewrite) 
- Contextual inference ("rename to camel case" should convert existing name, but asks user for the new name instead)
- No loading indicator during processing
- Large JSON schema may cause issues. Should be replaced with TOON.

## Implemented checks:

- `count_vertices`
- `rename_object`
- `select_hard_edges`
- `select_faces_with_intersecting_meshes`

## Setup

1. Edit > Preferences > Add-ons > Install > Select `vexa.zip`
2. Check the box next to "Vexa"
3. Expand the add-on, paste [Gemini API Key](https://aistudio.google.com/app/apikey)

## Usage

1. Open 3D Viewport Sidebar (Press `N`)
2. Find the Vexa tab
3. Select an object
4. Type an instruction
5. Click the Play button