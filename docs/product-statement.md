# Product statement

FECreator **is** a local-first workbench that turns text or concept art into
Fire Emblem GBA portraits through deterministic processing and human review.

FECreator **is not** a ROM editor, ROM builder, FEBuilderGBA replacement, hosted
image-generation service, or generic non-Fire-Emblem asset tool.

## v1 scope
- Asset plugin: `portrait`. Target spec: `fe-gba-portrait-standard`.
- Interfaces: JSON CLI, FastAPI HTTP, WebSocket, MCP server, thin agent skills.
- Providers: `manual`, `fake`, `mcp-client`, `command`.
- Deferred: unit icons, map sprites, battle sprites, weapon frames, LoRA, other platforms.
