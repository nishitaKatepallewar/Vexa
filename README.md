Goal:

- Build a system architecture that helps connect Blender with an LLM, locally. Refer to the system developed [here](https://www.linkedin.com/posts/julienchaumond_interact-with-blender-to-do-3d-modeling-activity-7324409403502190592-_-Y8?utm_source=share&utm_medium=member_desktop&rcm=ACoAAEXA4RUBaqHbzdHHlQXBub9hFI62j68wEpk) for a good standard reference.
- A golden reference is that of [CADAM](https://github.com/Adam-CAD/CADAM) which is an AI agent that converts text to 3D models on AutoCAD. CADAM uses a suite of sub-agents, each to deal with conversational answers, conversion of NLP queries into queries for the underlying Anthropic Claude model, writing a program for the core 3D model generation, final model rendering, etc. 

Some features to be integrated:

- Automatically make (atleast basic) corrections and optimizations upon user consent.

Steps to run VEXA:
- Open Blender, check on required APIs, and connect MCP server.
- ```git clone git@github.com:nishitaKatepallewar/Vexa.git```
- ```cd Vexa```
- ```source myevn/bin/activate```
- ```cd app/dist/```
- ```./Vexa```
