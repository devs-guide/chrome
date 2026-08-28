# Offline trusted-LAN operation

Offline operation is a first-class deployment of the generated `static/`
artifact, not a reduced HTTP mode.

The expected origin is:

```text
https://<LAN-IP>:8443/chrome/
```

The serving host creates a persistent private lab CA and replaceable LAN leaf
certificate. Only the public root certificate is installed on test devices;
private keys remain beneath ignored `.local/` state.

After artifact transfer and device trust provisioning, the LAN may be fully
disconnected from the internet. The server must not contact GitHub, certificate
services, package registries, analytics, or other remote services.

Device trust cannot be installed or bypassed by the Python server. Managed or
locked hardware must use its supported trust-provisioning mechanism.
