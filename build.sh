#!/bin/bash
# Build script to create vexa.zip for Blender add-on

rm -f vexa.zip
cd vexa && zip -r ../vexa.zip . -x "__pycache__/*" "*/__pycache__/*" "*.pyc"
echo "Created vexa.zip"
