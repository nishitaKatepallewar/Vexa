#!/bin/bash
# Build script to create vexa.zip for Blender add-on
# Run from Vexa/ directory: cd Vexa && vexa/build.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
rm -f vexa.zip  # zip -r adds to an existing archive, which would keep deleted files
zip -r vexa.zip vexa/ -x "vexa/__pycache__/*" "vexa/*/__pycache__/*" "vexa/*.pyc" "vexa/*/*.pyc" "vexa/build.sh" "vexa/vexa.zip"
echo "Created vexa.zip"
