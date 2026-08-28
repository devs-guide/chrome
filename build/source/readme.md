# Chromium source builds

Status: documentation foundation; executable build automation is deferred.

This path will own reviewed procedures for:

- installing `depot_tools` and checking out Chromium;
- selecting current, historical, or vendor-relevant revisions;
- installing platform build dependencies;
- configuring GN arguments and Chrome/Chromium feature flags;
- building with Ninja;
- retaining patches and reproducibility metadata;
- producing older or purpose-built browsers for device capability research.

Every future runbook must identify its host OS/architecture, Chromium revision,
toolchain, feature flags, output identity, external network requirements, and
verification evidence. A documented version is not accepted until the built
browser reports an identity and runs the relevant web laboratory.

Authoritative research begins with Chrome for Developers, Chromium source and
documentation, Chromium Issues, ChromeStatus, applicable standards, and MDN.

Public path: `https://devs-guide.github.io/chrome/build/source/`

Parent: [`../readme.md`](../readme.md)
