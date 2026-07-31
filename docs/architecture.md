# Architecture

Every interface calls one `FeCreatorApp` service, which composes registries
(assets/specs/providers), immutable jobs/workspaces, and a NumPy/OpenCV imaging
core. The registered asset plugins are `portrait` and `dialogue_background`; their
registered specs are `fe-gba-portrait-standard` and
`fe8-dialogue-background-source-240x160`. Both use the shared reviewed lifecycle
for planning, source submission, candidate review, and publication. The React/Vite
web app (bound to 127.0.0.1) is the human review UI, shipped as static assets in
the wheel.

Module map: see the file tree in `docs/superpowers/plans/2026-07-24-fecreator-v1-master.md` §3.
