# Touch diagnostics

Status: implemented `0.0.1` vertical slice; physical-device acceptance pending.

This path provides guided and directly selectable tests for browser/device
signals, secure-context state, a Pointer Events lifecycle, a Touch Events
lifecycle, live contact count/visualization, catalog expectations, and observed
behavior. Test IDs and result states are stable, versioned catalog data.

The application is a dependency-free offline-capable PWA. Progress and reports
stay in local storage unless explicitly exported. JSON may be imported/exported
and the report has a print/PDF view. Unavailable hardware/APIs are recorded
honestly rather than converted to false success.

Runtime sources are local. Documentation and edge-case research should begin
with [Chrome for Developers](https://developer.chrome.com/),
[MDN](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events), and the
[Chromium Issue Tracker](https://issues.chromium.org/issues).

Stable routes:

- `#/run`
- `#/tests`
- `#/test/environment.baseline`
- `#/test/pointer.lifecycle`
- `#/test/touch.lifecycle`
- `#/report`

Public path: `https://devs-guide.github.io/chrome/web/touch/`

Parent: [`../readme.md`](../readme.md)
