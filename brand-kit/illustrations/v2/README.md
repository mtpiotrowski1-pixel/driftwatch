# Generated empty-state illustrations, version 2

These two decorative raster illustrations were generated with the built-in
Codex imagegen tool on 2026-10-08. They are AI-generated symbolic artwork, not
hand-drawn assets, product screenshots, charts or proof of real deliveries.
The exact generation prompts are preserved in
[`EMPTY_STATE_IMAGEGEN_PROMPTS.json`](../../prompts/EMPTY_STATE_IMAGEGEN_PROMPTS.json).
No external API key or fallback CLI was used.

| Illustration | Original | Used by |
| --- | --- | --- |
| Workspace | `sources/empty-workspace.png` | Empty project/workspace view |
| Delivery | `sources/empty-delivery.png` | Empty recipient/delivery view |

Originals retain the imagegen alpha channel at 1536 × 1024. Node sharp exports
480 × 320 and 960 × 640 PNG/WebP variants without flattening alpha or redrawing
the scene. WebP and the PNG fallback are used by
`web/src/components/brand/EmptyStateArtwork.tsx` through responsive `<picture>`
markup with an empty alt attribute, because the surrounding UI supplies the
meaningful title, description and action. Existing data charts retain their
actual data rendering.

The checked-in `web/exports.json` records dimensions and file sizes. The same
exports are copied into `web/public/brand/illustrations` for deployment. The
original vector illustrations remain in `brand-kit/illustrations`; they have
not been deleted or presented as newly generated bitmaps.

Re-exporting is optional and requires Node.js plus `sharp`, not Python:

```sh
node brand-kit/tools/export_empty_states.mjs --sharp-module /path/to/node_modules/sharp
```

Run this from the repository root. If `sharp` is available to the script's normal
Node module resolution, omit `--sharp-module`. Application installation and
startup do not require this asset authoring dependency.
