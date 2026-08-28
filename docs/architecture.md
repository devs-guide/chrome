# Architecture

The repository has four canonical source families:

| Source | Owner |
|---|---|
| `www/` | Root public landing page and shared site styling |
| `web/` | Runnable static browser laboratories |
| `build/` | Chromium build/source documentation |
| `docs/` | Project and contributor documentation |

`actions/www.pages.sh` assembles these sources into ignored `static/`. Both
GitHub Pages and the Python LAN HTTPS tool consume that exact artifact.

Normal browser labs have no application backend or required external runtime
dependency. Features that genuinely require a protocol server remain separate
tools and must not expand the static server implicitly.
