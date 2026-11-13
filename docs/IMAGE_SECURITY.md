# Image security and native dependency maintenance

CI fails the image job on any HIGH or CRITICAL finding that Trivy reports in the API, worker or firewall image, including advisories the vendor has not fixed yet. There is no CVE allowlist or severity override. Keep the complete reports and the SPDX SBOMs with the deployed image digests. A clean scan reflects the advisory database at scan time; it does not prove that every embedded browser component is free of defects.

## Base images

The API and worker images run on a digest-pinned, glibc-based Wolfi image. Every installed package is pinned in [docker/native/api.apk.lock](../docker/native/api.apk.lock) and [worker.apk.lock](../docker/native/worker.apk.lock). During the build, `verify_runtime.py` fails if the installed packages differ from the lock in any name or version. It also checks that ACL, CUPS, Perl and Xvfb are absent, that CPython loads Expat 2.9.0 or newer, and that the timezone database resolves UTC and Europe/Warsaw. Only Linux x86_64 images are built and validated.

The worker installs Playwright's headless shell (`--only-shell`), so the image has no headed browser, Xvfb or printing packages. Its lock lists Wolfi's library subpackages such as `libnspr`, `libnss` and `libatk-bridge-2.0` explicitly, because the similarly named `nss` and `at-spi2-core` packages do not provide the shared libraries Chromium loads. Wolfi is not among Playwright's officially supported distributions, so `verify_browser.py` resolves every dynamic dependency of the shipped browser and driver binaries during the build, and the Docker smoke test launches Chromium under the deployed isolation. Fonts cover Noto Sans Latin/Polish, Arabic, CJK and emoji; other scripts depend on website fonts, and text extraction preserves Unicode either way.

The firewall image runs on digest-pinned Alpine 3.24. Alpine's repository keeps only the newest revision of each package, so the build upgrades the base packages and installs `iptables` with a minimum `zlib` version (the [vendor fix](https://secdb.alpinelinux.org/v3.24/main.json) for CVE-2026-85091) instead of exact pins.

## History

The images moved from Debian 13 to Wolfi on 2026-10-08. The Debian base still carried 8 distinct HIGH/CRITICAL advisories in the API image and 24 in the worker image. [known-cves.json](../docker/native/known-cves.json) records each of them and how it was resolved. Two of them, in libX11 and libXrender, had no published release at the time and were patched locally until Wolfi shipped libX11 1.8.14 and libXrender 0.9.13; the images now use those vendor packages.

The application also stopped using lxml, whose wheel embedded its own copy of libxml2 that system updates could not fix. BeautifulSoup parses captured fragments with the standard library's `html.parser`; the cleaner, extraction and real-browser tests cover the change. The source installers remove a leftover lxml only from the checkout's own `.venv`; see [installation](INSTALL.md).

## Refreshing the locks

New advisories against pinned packages fail the image job until the locks move to fixed versions. From the repository root on an x86_64 Docker host:

```sh
sh docker/native/refresh_locks.sh
```

The script installs the package names from each lock, without versions, into the pinned Wolfi base and writes back what was installed, including new dependencies. Review the diff: new packages should be dependencies of existing ones, and nothing from the removed list above may return. Then rebuild the three images and run the checks below before committing. Prefer a vendor-fixed package to a local patch.

## Reproduce the CI checks

```sh
docker build --target runtime -t driftwatch:release .
docker build --target capture-worker -t driftwatch-capture:release .
docker build --target capture-firewall -t driftwatch-firewall:release .
docker run --rm --entrypoint python driftwatch:release /native/verify_runtime.py api
docker run --rm --entrypoint python driftwatch-capture:release /native/verify_runtime.py worker
python scripts/docker_smoke.py --no-build
for image in driftwatch:release driftwatch-capture:release driftwatch-firewall:release; do
  trivy image --scanners vuln --ignore-unfixed=false --severity HIGH,CRITICAL --exit-code 1 "$image"
  trivy image --format spdx-json --output "${image%:release}.spdx.json" "$image"
done
```

Use the Trivy version pinned in CI and keep its advisory database timestamp with the reports. The smoke test runs real Chromium through a baseline, a change and a delivery against an owned HTTP fixture, and checks that the firewall blocks forbidden sockets. No paid provider is called.

The API and worker run as non-root users, without capabilities and with read-only filesystems. The worker holds only its capture-service token and the fill values for approved origins; it has no database, OpenAI, mail, billing, session-signing or encryption credentials, and it shares the firewall's filtered network namespace. These controls stay necessary after library fixes, because they limit what a compromised browser can reach. Pip and ensurepip are removed from both images after `pip check`; the signed Wolfi `py3-pip-wheel` package stays in the native inventory.
