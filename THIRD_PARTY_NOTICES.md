# Third-party notices

Driftwatch's own application code, documentation and original project artwork
use [PolyForm Noncommercial 1.0.0](LICENSE). This does not replace or restrict the
licenses of independently licensed third-party materials listed below.

## Fonts

Manrope and Source Sans 3 retain the SIL Open Font License 1.1. Their copyright
notices, full licenses and upstream provenance are shipped in
[web/public/fonts](web/public/fonts). Preserve those files with font copies.

## Runtime and development dependencies

Python and JavaScript dependencies retain their upstream licenses and copyright
notices. The exact package versions and hashes are recorded in the
`requirements*.lock` files and [web/package-lock.json](web/package-lock.json).
Packages are installed from their upstream distributions rather than relicensed
as Driftwatch source.

Examples requiring their own notices include the LGPL-licensed psycopg driver,
MPL-licensed certifi, pathspec and Lightning CSS, and the CC BY-licensed
caniuse-lite data. The noncommercial restriction on Driftwatch does not apply to
these packages when used separately under their own licenses. When redistributing
installed dependencies or container images, retain their license files and meet
any corresponding-source, attribution and replacement requirements applicable
to those components. A lockfile identifies versions; it does not replace the
upstream license text.

## Operating system packages

The container images install Wolfi and Alpine packages, including Chromium's
system libraries, from the vendors' signed repositories. Each package keeps its
upstream license. The installed versions are listed in
[docker/native](docker/native) and in the SBOMs that CI generates for each image.

## Project artwork

Artwork originals, concise generation provenance and optional export recipes
are preserved in the [brand kit](brand-kit/README.pl.md). Bundled fonts and any
separately attributed third-party material remain subject to their own notices, even when used in
the project's visual identity.
