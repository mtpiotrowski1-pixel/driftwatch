# Image security and native dependency maintenance

CI rejects every reported HIGH/CRITICAL image vulnerability, including vendor-unfixed advisories. There is no CVE allowlist, package database editing, invented upstream version, or severity override. Keep complete reports and SPDX SBOMs with the exact deployed image digests. A clean scan depends on its advisory database and cannot establish that every embedded browser component is defect-free.

## Why the runtime changed

The 2026-10-08 Debian 13 baseline, after removing unused pip/ensurepip modules, still had these unfixed-inclusive Trivy 0.75.0 findings:

| Target | HIGH package/CVE pairs | CRITICAL pairs | Distinct CVEs |
| --- | ---: | ---: | ---: |
| API | 44 | 0 | 8 |
| Browser worker | 62 | 1 | 24 |
| Firewall | 0 | 0 | 0 |

The Python targets now use a digest-pinned, glibc-based Wolfi image and exact native package locks under [docker/native](../docker/native). Wolfi is a maintained package collection, not an LTS distribution with a fixed release number. Changing locks requires fresh scans and actual browser compatibility checks. The Docker build validates Linux x86_64 and rejects other native architectures; source installation remains separate.

The worker installs Playwright 1.63's headless shell with `--only-shell`, avoiding the headed browser, Xvfb and printing packages. Wolfi is outside Playwright's official Ubuntu/Debian OS support list: compatibility is an application test obligation, not upstream OS certification. Source installers retain full Chromium for the headed local picker.

The worker's complete 89-package lock explicitly includes Wolfi's `libnspr`, `libnss`, `libatk-1.0` and `libatk-bridge-2.0` library subpackages. The similarly named `nss` and `at-spi2-core` packages alone do not provide the browser's required shared libraries. `verify_browser.py` uses the glibc loader to reject unresolved recursive dependencies in every shipped dynamic browser/driver ELF, including bundled shared libraries; the separate runtime smoke must also launch Chromium under the deployed isolation controls.

The common native base includes signed, pinned `tzdata=2026e-r0`: Python's `ZoneInfo` needs the IANA database even for the default UTC scheduler and notification delivery. The complete inventories are 35 packages for API, 89 for worker and 99 for builder. `verify_runtime.py` checks UTC and Europe/Warsaw availability during every role's build; the runtime smoke also exercises baseline, changed data and actual notification delivery.

Fonts cover Noto Sans Latin/Polish, Arabic, CJK and emoji. Other scripts depend on website fonts or fallback coverage; HTML text extraction preserves Unicode independently of fonts.

## All 24 prior advisories

[known-cves.json](../docker/native/known-cves.json) records every identifier, its concrete treatment and primary references. Repeated source-package findings account for the larger binary package/CVE pair counts.

| Component | Prior CVEs | Current treatment |
| --- | ---: | --- |
| util-linux libraries | 4 | 2.42.4, including the completed nsenter fix after 2.42.3 |
| ncurses | 1 | 6.6.20260926, newer than the 20251213 fix |
| systemd libraries | 1 | Worker 261.3, newer than 261.2; absent from API |
| Expat | 4 | 2.9.0; CPython uses this system library |
| libxml2 | 8 | Worker libxml2-16 2.15.4; conflicting old libxml2 excluded |
| ACL, Perl, CUPS, Xvfb | 4 | Packages and corresponding libraries/executables absent |
| libX11, libXrender | 2 | Exact upstream fixes described below |

The application also removed lxml: its Python wheel embedded an older libxml2 independently of the system package. Updating only the system library did not repair that copy. BeautifulSoup now uses Python's maintained `html.parser` for captured HTML fragments; no XML/XPath/XSLT functionality needed lxml. Cleaner, extraction, record association, malformed fragment and actual browser regression tests cover this change. An upgraded site's serialized DOM may differ; extracted records still determine meaningful changes.

Source upgrades remove the obsolete lxml distribution only inside the checkout's own supported `.venv`, then reject any remaining import or distribution metadata. Unsupported, shared or linked environments are preserved and rejected before dependency updates; see [installation](INSTALL.md).

Primary evidence includes [util-linux 2.42.4](https://github.com/util-linux/util-linux/blob/v2.42.4/Documentation/releases/v2.42.4-ReleaseNotes), [Expat 2.9.0](https://github.com/libexpat/libexpat/blob/R_2_9_0/expat/Changes), [systemd's advisory](https://github.com/systemd/systemd/security/advisories/GHSA-jm29-p7hh-vjhv) and [libxml2 2.15.4](https://gitlab.gnome.org/GNOME/libxml2/-/blob/v2.15.4/NEWS).

Full reports also identified two MEDIUM advisories beyond that HIGH/CRITICAL baseline. Runtime and development locks now use Mako 1.4.3, above the [upstream 1.4.2 fix](https://github.com/sqlalchemy/mako/security/advisories/GHSA-5639-2j2p-m4mx) for CVE-2026-102991. The firewall installs signed Alpine `zlib=1.3.2-r1`, the [vendor security-database fix](https://secdb.alpinelinux.org/v3.24/main.json) for CVE-2026-85091. These remain visible to normal scanners, without exceptions.

## Two transparent upstream backports

Published libX11 1.8.14/libXrender 0.9.13 tarballs were unavailable on 2026-10-08. The recipe applies [libX11 MR309](https://gitlab.freedesktop.org/xorg/lib/libx11/-/merge_requests/309) and [libXrender MR19](https://gitlab.freedesktop.org/xorg/lib/libxrender/-/merge_requests/19) to the stable published tarballs. [backports.json](../docker/native/backports.json) pins both source and patch SHA-256 digests. Patches apply with zero fuzz; the locked builder runs configure, make and upstream make check, then strips debug data.

Packages keep actual upstream versions and Wolfi revisions: `1.8.13-r7` and `0.9.12-r9`. A local tagged repository replaces them through apk with newly generated file checksums, dependencies and SONAME provides. The recipe never writes `/lib/apk/db` directly. Descriptions and installed provenance explicitly identify the Driftwatch backport.

Wolfi's pinned apk-tools 2.14 reads APKv2; Alpine 3.24's `apk mkpkg` emits APKv3. The small recipe therefore emits documented APKv2 control/data streams with per-file and symlink checksums. Actual apk installation validates that format. Only the local packages copied from the hash-verified builder are allowed unsigned, in a separate **offline** transaction. Its dedicated `--repositories-file` lists only the local tagged directory: vendor indexes cannot be fetched under `--allow-untrusted`, including apk-tools 2.14's index-loading behavior with `--no-cache`. Official packages are installed first with normal signature checks.

`/usr/share/driftwatch/native/{libx11,libxrender}.json` records source/patch URLs and hashes, the addressed CVE, and installed ELF SHA-256 hashes. Upstream license files remain installed. `verify_backports.py` rejects mismatched binaries. `verify_runtime.py` checks the complete native inventory and removed components against the committed locks. These checks supplement scans; they do not suppress future findings against an unchanged upstream version.

Prefer corrected vendor packages when available and remove the corresponding custom backport. Review source bounds, build flags, dependencies and SONAMEs when changing recipes. Never inflate a revision to outrank future updates. Rebuild the toolchain from its own lock.

## Reproduce

```sh
docker build --target runtime -t driftwatch:release .
docker build --target capture-worker -t driftwatch-capture:release .
docker build --target capture-firewall -t driftwatch-firewall:release .
python scripts/docker_smoke.py --no-build
for image in driftwatch:release driftwatch-capture:release driftwatch-firewall:release; do
  trivy image --scanners vuln --ignore-unfixed=false --severity HIGH,CRITICAL --exit-code 1 "$image"
  trivy image --format spdx-json --output "${image%:release}.spdx.json" "$image"
done
```

Use CI's pinned Trivy version and retain its advisory database timestamp. The smoke exercises real Chromium, baseline/change extraction and delivery against an owned HTTP fixture, plus actual forbidden sockets blocked by the firewall. No paid providers are called.

API and worker remain non-root, without capabilities and with read-only filesystems. The worker has its own capture-service token and ephemeral fill values for approved origins; it has no application database, OpenAI, mail, billing, session-signing or encryption credentials. It shares the firewall's filtered network namespace. These controls remain necessary after library fixes and do not rule out browser compromise. Pip/ensurepip modules are removed after pip check; the signed Wolfi py3-pip-wheel package remains visible in the native inventory.
