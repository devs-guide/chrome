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

## Host workflow

Build once, provision explicit identities, inspect the setup, and serve:

```bash
bash actions/www.pages.sh
python3 tools/lan_https.py init --ip 192.168.50.20 --dns chrome.test
python3 tools/lan_https.py doctor \
  --ip 192.168.50.20 --bind 0.0.0.0 --port 8443 --root static
python3 tools/lan_https.py serve \
  --ip 192.168.50.20 --bind 0.0.0.0 --port 8443 --root static
```

Copy only `.local/lan-https/ca/root-ca.cert.cer` to the target device and
verify the displayed SHA-256 fingerprint before installing trust. Never copy
`root-ca.key.pem`. A host-side `doctor` pass proves the TLS chain, requested
identity, and artifact bytes; it does not prove that an external device trusts
the CA.

If an IP or DNS identity changes, use `renew` with the complete desired SAN
set. The root CA remains stable, so already provisioned devices normally trust
the replacement leaf. `reset-ca` intentionally requires a destructive typed
confirmation and means every device must be provisioned again.

The remote device clock must fall between the reported certificate Not Before
and Not After values. A locked device that cannot import a private CA requires
its supported vendor/MDM trust mechanism; bypassing certificate validation or
accepting an interstitial is not a valid test setup.
