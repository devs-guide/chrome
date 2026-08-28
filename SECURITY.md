# Security policy

## Reporting

Report security issues privately through the repository's GitHub security
advisory interface. Do not include credentials, private keys, private device
reports, or sensitive hardware identifiers in public issues.

## Repository guarantees

- Private keys and `.local/` certificate state are never committed or published.
- The project never distributes a universal trusted CA or bypasses browser PKI.
- Browser diagnostics remain local unless an operator explicitly exports them.
- Browser labs contain no telemetry, analytics, or required remote runtime assets.
- Permission and hardware-write tests require an explicit user action.

The LAN HTTPS tool proves host-side certificate and artifact readiness. Device
trust installation is an external provisioning action and must be verified on
the device itself.
