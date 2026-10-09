# Interface gallery

These are actual browser views from an isolated local instance with synthetic
organizations and data. Capture, AI and delivery adapters are scripted; the
screenshots do not demonstrate a live paid provider or production deployment.
The interface is Polish here and also provides English translations. Desktop
views use 1440 CSS px; mobile views use 320–375 CSS px. Chrome was at 90%
zoom; the manifest records CSS and exported bitmap dimensions separately. Only the capture canvas outside the
viewport is trimmed; the interface is not retouched. [manifest.json](manifest.json)
records image hashes, geometry, fonts and the build captured for each view.

All views use the final Emerald Portal branding generated with `image_gen` on
2026-10-08. The [brand kit](../../brand-kit/README.pl.md) preserves the source
images, concise generation provenance and optional export recipes. Decorative
artwork stays behind actual HTML controls and text; it does not represent live
monitoring results.

## Sign in and public landing page

![First administrator setup on a new installation](initial-setup-desktop.jpg)

![Sign-in page](login-desktop.jpg)

![Public landing page with an explicitly marked demo](landing-desktop.jpg)

## Monitoring and evidence

![Dashboard with synthetic monitoring history](dashboard-desktop.jpg)

![Selected older event in the synthetic history; AI is disabled](history-desktop.jpg)

## Responsive views and empty states

| Dashboard | Change history |
|---|---|
| ![Mobile dashboard](dashboard-mobile.jpg) | ![Mobile change history](history-mobile.jpg) |

| Projects | Recipients |
|---|---|
| ![Mobile empty projects](empty-projects-mobile.jpg) | ![Mobile empty recipients](empty-recipients-mobile.jpg) |

![Empty projects with responsive bitmap artwork](empty-projects-desktop.jpg)

![Empty recipients with responsive bitmap artwork](empty-recipients-desktop.jpg)

The 320 px view below was separately checked with a classic desktop scrollbar.
Content and document widths match; the manifest records the measured dimensions.

![Dashboard at a 320 px viewport](dashboard-320.jpg)

![First administrator setup at a 320 px viewport](initial-setup-mobile.jpg)

## Access and account recovery

![Registration closes after setup unless the owner explicitly enables it](access-desktop.jpg)

![Password recovery with readable text over the generated background](forgot-password-desktop.jpg)
