# Profile edge offset

Lets each profile be displaced from its path edge in the edge frame, alongside the existing anchor, rotation and mirrors.
Branch: `feat/profile-edge-offset`.

## Specs

- S1. "ademas de roptacion me gustaria tener controles para podes desplazar el perfil respecto a la arista" — two distance controls (horizontal and vertical) displace the profile from its edge.
- S2. The offset stays in the edge frame ("quede en el marco" de la arista): rotating or mirroring the section does not change the direction of the displacement.
- S3. "Sin migraciones, no hemos lanzado la primer release aun." — no `onDocumentRestored`/compatibility migration for the new properties.
- S4. "Dejemoslo para despues, luego de terminar con la creacion de perfiles encararemos una revision, modernizacion y refactorizacion de ingletes." — end-miter/trim code is out of scope.
- S5. The offset is per edge like rotation and mirrors: stored per selected edge, shown as mixed when selected edges differ, applied on creation, Apply and edit.
- S6. The alignment preview shows where the edge lies relative to the displaced section; help docs describe the new controls.

## Tasks

- T1 (S1, S2, S3) Profile model: `OffsetX`/`OffsetY` distances bound to `AttachmentOffset.Base`, native tests. Route: inline. Commit: pending.
- T2 (S1, S5) Create/edit task panel: per-edge offset controls, mixed state, creation/update/edit load, tests. Route: inline. Commit: pending.
- T3 (S6) Alignment preview marker and docs. Route: inline. Commit: pending.

## Log

- L1. User: "ademas de roptacion me gustaria tener controles para podes desplazar el perfil respecto a la arista, que opinas? pros contras? opciones?"
- L2. User, on edge frame vs profile frame: "quede en el marco" (edge frame, recommended option).
- L3. User: "1. Sin migraciones, no hemos lanzado la primer release aun. 2. Dejemoslo para despues, luego de terminar con la creacion de perfiles encararemos una revision, modernizacion y refactorizacion de ingletes."
- L4. Profiles attach with `MapMode = "NormalToEdge"`; rotation is `AttachmentOffset.Rotation.Angle`. A Placement rotates then adds `Base`, so `AttachmentOffset.Base.x/y` is the edge frame and does not rotate with the section.
