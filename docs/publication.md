# Publication

The publication contract is:

```text
source → build once → validate once → deploy that exact artifact
```

The public site is rooted at `https://devs-guide.github.io/chrome/`. The source
tree never treats the generated `www` branch or local `static/` directory as an
editable owner.

Required stable paths include the root landing page, `web/touch`, its catalog
and report schema, Chromium source-build docs, documentation, and publication
metadata/checksums.

Feature previews are opt-in, exact-SHA artifacts under `_preview/`; they must
not overwrite the canonical main tree. The manual preview workflow accepts a
strict lowercase label, an exact remote commit SHA, and a matching typed
confirmation. Canonical publication likewise requires a typed confirmation for
manual rollback/republication. Defining these workflows does not authorize
enabling Pages or running either publisher; those remain human review gates.
