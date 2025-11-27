Goal:

- Build a system architecture that helps connect Blender with an LLM, locally. Refer to the system developed [here](https://www.linkedin.com/posts/julienchaumond_interact-with-blender-to-do-3d-modeling-activity-7324409403502190592-_-Y8?utm_source=share&utm_medium=member_desktop&rcm=ACoAAEXA4RUBaqHbzdHHlQXBub9hFI62j68wEpk) for a good standard reference.

Some features to be integrated:

- Automatically make (atleast basic) corrections and optimizations upon user consent.

Steps to run VEXA:
- Open Blender, check on required APIs, and connect MCP server.
- ```git clone git@github.com:nishitaKatepallewar/Vexa.git```
- ```cd Vexa```
- ```source myevn/bin/activate```
- ```cd app/dist/```
- ```./Vexa```
