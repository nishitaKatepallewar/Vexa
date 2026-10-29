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

Changes to the code reload automatically in Blender

### Production
1. Build the zip (run from Vexa directory):
   ```bash
   cd Vexa
   ./vexa/build.sh
   ```
2. In Blender: Edit > Preferences > Add-ons > Install > Select `vexa.zip` > Check the box to enable

No account or API key is needed. All checks and fixes run locally.

## Usage

1. Open 3D Viewport Sidebar (Press `N`)
2. Find the Vexa tab
3. Select an object
4. Click a check

## Optional: AI assistant

To type instructions in plain English instead of clicking checks:

1. Expand Vexa in Edit > Preferences > Add-ons
2. Paste a [Gemini API Key](https://aistudio.google.com/app/apikey)

An "Ask Vexa (AI)" box then appears in the panel. Without a key it stays hidden.
