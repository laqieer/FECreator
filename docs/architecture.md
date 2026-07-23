# Architecture

Every interface calls one `FeCreatorApp` service, which composes registries
(assets/specs/providers), immutable jobs/workspaces, a NumPy/OpenCV imaging core,
the portrait plugin, and the `fe-gba-portrait-standard` spec. The React/Vite web
app (bound to 127.0.0.1) is the human review UI, shipped as static assets in the wheel.

Module map: see the file tree in `docs/superpowers/plans/2026-07-24-fecreator-v1-master.md` §3.
