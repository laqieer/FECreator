# Product statement

FECreator **is** a local-first workbench that turns text or concept art into
Fire Emblem GBA portraits and FE8 dialogue-background source packages through
deterministic processing and human review.

FECreator **is not** a ROM editor, ROM builder, FEBuilderGBA replacement, hosted
image-generation service, or generic non-Fire-Emblem asset tool.

## v1 scope
- Asset plugins: `portrait`, `dialogue_background`. Target specs:
  `fe-gba-portrait-standard`, `fe8-dialogue-background-source-240x160`.
- Dialogue backgrounds end at deterministic opaque 240×160 source packages. FE8
  color reduction, palette banks, TSA conversion, and ROM integration are
  downstream concerns.
- Interfaces: JSON CLI, FastAPI HTTP, WebSocket, MCP server, thin agent skills.
- Providers: `manual`, `fake`, `mcp-client`, `command`.
- Deferred: unit icons, map sprites, battle sprites, weapon frames, LoRA, other platforms.
