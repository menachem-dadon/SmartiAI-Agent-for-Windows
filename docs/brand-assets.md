# Smarti brand assets

`assets/smarti.svg` is the unmodified icon supplied by the user on 2026-11-05.
It is the source for all shipped application artwork. Keep its gradients,
filters, rounded corners and transparency intact.

Regenerate from the repository root with:

```powershell
python scripts/generate_brand_assets.py
```

The generator needs Pillow, Python Playwright and installed Microsoft Edge.
These are development dependencies only. Edge renders at twice the SVG's
1024-pixel viewBox resolution to preserve its turbulence, blur and blend effects;
Pillow downsamples and encodes the committed assets. No renderer is needed at
runtime or during ordinary builds.

| Asset | Consumers |
|---|---|
| `assets/logo.png` (1024px RGBA) | React sidebar and About, startup fallback, legacy Qt logo/splash/notifications |
| `desktop/public/loading-icon.png`, `loading-icon-dark.png` (256px RGBA) | Static startup artwork in either theme, at the same 72px display size |
| `assets/loading-icon.png.png` (256px RGBA) | Existing compatibility copy of the startup artwork |
| `assets/smarti.ico` | Legacy Windows executable, installer and notification identity |
| `desktop/src-tauri/icons/icon.ico` | Tauri Windows executable, installer, shortcuts, window and tray |
| `desktop/src-tauri/icons/*.png` | Tauri 32/128/256/1024px icons, Windows Square logos and StoreLogo |
| `desktop/src-tauri/icons/icon.icns` | Existing Tauri ICNS bundle asset |
| `desktop/public/favicon.ico` | Browser tab when opening the source interface |

Each ICO contains 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256px RGBA frames.
The supplied square artwork is used without cropping or recoloring. Both
startup themes use the same transparent artwork; the old dark-image screen
blend and size compensation no longer apply. Control icons and provider logos
keep their existing sources.
