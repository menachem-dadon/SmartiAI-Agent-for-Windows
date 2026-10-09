# Shared artwork and fonts

Copyright (c) 2026 Elazar. All rights reserved.

The outline artwork in `icons/` is the original artwork authored for Smarti's
accepted UX-1 v7 direction. UX-2 moves those exact PNG files here without edits.
The source geometry remains in `scripts/generate_ux1_icons.py`.
These files are covered by the existing repository license and required notices:
see the root `LICENSE` (PolyForm Noncommercial License 1.0.0 and project notice).
These original PNGs remain preserved unchanged and selectable as the `original`
family after the user's later request to use Tabler SVG.

## Tabler SVG family

The default family uses the official `@tabler/icons-react` 3.48.0 package,
with unmodified SVG geometry and a semantic action/tool mapping in `icons.tsx`.
Source: https://github.com/tabler/tabler-icons/tree/v3.48.0
Copyright (c) 2020-2026 Paweł Kuna. Licensed under MIT.
The complete copyright, permission and warranty notice is preserved in
`desktop/public/licenses/tabler-icons-MIT.txt`. Vite copies this public asset
into frontendDist; Tauri includes frontendDist in its normal package.
The repository's own license does not replace the MIT license on this artwork.
No CDN, icon font or downloaded font is used.

## Provider identification artwork

The 18 SVG files in `src/provider-icons/` were copied unchanged from the user's
`ai-provider-icons.zip` (core directory). Its supplied provenance identifies
Lobe Icons by LobeHub, MIT licensed, except the pack's generic local-server icon.
The supplied complete notice is preserved in
`desktop/public/licenses/lobe-icons-MIT.txt` and copied by Vite into frontendDist.
These marks identify existing integrations in settings. Monochrome rendering
inherits the active theme; artwork geometry is unchanged. The action/tool icon
family stays Tabler and the original Smarti PNG family stays preserved.

Segoe UI, Arial, Consolas and Courier New are CSS system fallbacks only. Smarti
does not redistribute their font files through this design system.

## Buy Me a Coffee identification artwork

`desktop/public/brands/buy-me-a-coffee.svg` contains the official cup geometry
from https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js, the button embed
supplied by the user. The coffee fill is white, matching the supplied
`data-coffee-color="#ffffff"` option; the outline geometry and color are preserved.
Brand kit: https://buymeacoffee.com/brand
The logo and Buy Me a Coffee name belong to their respective owner and identify
the user's support link. The repository license does not replace rights in
these marks. Vite bundles the static SVG; no third-party script, font or runtime
image request is used by the support button.
