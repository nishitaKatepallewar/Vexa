# Vexa (v0.1)

QC checks in seconds.

**Architecture**

![System Architecture](assets/architecture_v0.1.png)

1. Type a prompt in Blender's N-Panel
2. Prompt + available functions sent to LLM as JSON schema
3. LLM returns structured function call
4. Vexa executes the function in Blender
5. Result displayed in panel

AI interpretation remains separate from Blender operations.

**What works:**
- Maps natural language to function calls ("how many verts" → `count_vertices()`) 
- Fuzzy matching handles minor output variations
- Zero external dependencies, runs natively in Blender

**What doesn't:**
- Contextual inference ("rename to camel case" should convert existing name, but asks user for the new name instead)
- No loading indicator during processing
- Only 2 functions implemented: `rename_object` and `count_vertices`
