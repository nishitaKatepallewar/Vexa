# Vexa

QC checks in seconds.

## Setup

### Development 
1. Remove any existing `vexa` folder if present:
   ```bash
   rm -rf ~/.config/blender/<version>/scripts/addons/vexa
   ```
2. Create a symlink from Blender's addons folder to this directory:
   ```bash
   ln -s /path/to/Vexa/vexa ~/.config/blender/<version>/scripts/addons/vexa
   ```
3. In Blender: Edit > Preferences > Add-ons > Search "Vexa" > Check the box to enable
4. Expand the add-on, paste [Gemini API Key](https://aistudio.google.com/app/apikey)

Changes to the code reload automatically in Blender

### Production
1. Build the zip (run from project root):
   ```bash
   ./build.sh
   ```
2. In Blender: Edit > Preferences > Add-ons > Install > Select `vexa.zip` > Check the box to enable
4. Expand the add-on, paste Gemini API Key


## Usage

1. Open 3D Viewport Sidebar (Press `N`)
2. Find the Vexa tab
3. Select an object
4. Type instruction → Click Play, **OR** click a quick action button
