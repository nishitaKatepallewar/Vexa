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

1. Open 3D Viewport Sidebar (Press `N`) and find the Vexa tab
2. Pick a **Target**: General clean-up, Unity Asset Store, Fab or Unreal project
3. Choose what to check: Selected, Collection or Scene
4. Click **Check Assets**
5. For each problem: hover **?** to see why it matters, click the arrow to select the problem faces, or the wrench to apply a safe fix. **Fix All Safe Issues** does every safe fix at once.

Individual tools and checks are also under **Tools** as one-click buttons.

Studios can share their own targets: put preset `.json` files in a folder and set it under Preferences → Team presets folder. See `vexa/README.md` for the format.

## Tests

```bash
blender -b --factory-startup -P tests/run_all.py
```

## Optional: AI assistant

To type instructions in plain English instead of clicking checks:

1. Expand Vexa in Edit > Preferences > Add-ons
2. Pick a provider (currently Google Gemini) and paste its API key, e.g. a [Gemini API key](https://aistudio.google.com/app/apikey)
3. Optionally set a model; leave it empty to use the provider's default

An "Ask Vexa" box then appears in the panel. Without a key it stays hidden.
