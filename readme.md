# [devs-guide/chrome](https://devs-guide.github.io/chrome/)

> Runnable Chrome/Chromium web laboratories, capability diagnostics, and
> source-build documentation.

## Repository structure

- [`web/`](web/) — static browser laboratories and working examples.
  - [`web/touch/`](web/touch/) — the first implemented diagnostic suite.
  - [`web/app/`](web/app/), [`web/extension/`](web/extension/),
    [`web/pwa/`](web/pwa/), [`web/rtc/`](web/rtc/), and [`web/wasm/`](web/wasm/)
    are reserved feature families.
- [`build/`](build/) — Chromium source, revision, toolchain, and feature-flag guides.
- [`docs/`](docs/) — repository architecture, publication, testing, and contribution guidance.
- [`www/`](www/) — source for the public landing page.
- `static/` — generated, validated Pages artifact; never edit or commit it.

## URL paths

- [devs-guide.github.io/chrome/](https://devs-guide.github.io/chrome/)
- [devs-guide.github.io/chrome/web/](https://devs-guide.github.io/chrome/web/)
- [devs-guide.github.io/chrome/web/touch/](https://devs-guide.github.io/chrome/web/touch/)
- [devs-guide.github.io/chrome/build/source/](https://devs-guide.github.io/chrome/build/source/)

The same generated `static/` tree is served offline at
`https://<LAN-IP>:8443/chrome/` after explicit private-CA provisioning.

## Project rules

- Runtime applications use static HTML, CSS, vanilla JavaScript modules, and local assets.
- Browser behavior is exercised and observed rather than inferred from a user-agent string.
- GitHub Pages and trusted LAN HTTPS are equal delivery mechanisms for one artifact.
- Physical-device evidence remains distinct from repository and CI checks.

See [`docs/readme.md`](docs/readme.md) for the documentation index and
[`SECURITY.md`](SECURITY.md) before working with certificates or device data.
