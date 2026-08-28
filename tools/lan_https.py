#!/usr/bin/env python3
"""Provision a private lab CA and serve the Pages artifact over trusted LAN HTTPS."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import http.client
import http.server
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = 1
ROOT_DAYS = 3650
LEAF_DAYS = 397
EXPIRY_WARNING_DAYS = 30
PRIVATE_MARKERS = tuple(
    b"-----BEGIN " + kind + b"PRIVATE KEY-----"
    for kind in (b"", b"RSA ", b"EC ", b"ENCRYPTED ")
)


class LanHttpsError(RuntimeError):
    """A concise operator-facing failure."""


@dataclass(frozen=True)
class Paths:
    state: Path
    ca_dir: Path
    server_dir: Path
    openssl_dir: Path
    ca_key: Path
    ca_cert: Path
    ca_der: Path
    server_key: Path
    server_cert: Path
    server_csr: Path
    server_chain: Path
    server_ext: Path
    state_json: Path


@dataclass
class Check:
    id: str
    status: str
    message: str
    remediation: str | None = None


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def state_paths(state_dir: Path) -> Paths:
    state = state_dir.expanduser().resolve()
    ca_dir = state / "ca"
    server_dir = state / "server"
    openssl_dir = state / "openssl"
    return Paths(
        state=state,
        ca_dir=ca_dir,
        server_dir=server_dir,
        openssl_dir=openssl_dir,
        ca_key=ca_dir / "root-ca.key.pem",
        ca_cert=ca_dir / "root-ca.cert.pem",
        ca_der=ca_dir / "root-ca.cert.cer",
        server_key=server_dir / "server.key.pem",
        server_cert=server_dir / "server.cert.pem",
        server_csr=server_dir / "server.csr.pem",
        server_chain=server_dir / "server-chain.pem",
        server_ext=openssl_dir / "server.ext",
        state_json=state / "state.json",
    )


def ensure_openssl() -> str:
    executable = shutil.which("openssl")
    if not executable:
        raise LanHttpsError("openssl is required for certificate provisioning and diagnostics")
    result = subprocess.run(
        [executable, "version"], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise LanHttpsError(f"openssl is not usable: {result.stderr.strip() or result.stdout.strip()}")
    return executable


def run_openssl(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    executable = ensure_openssl()
    result = subprocess.run(
        [executable, *arguments], input=input_bytes, capture_output=True, check=False
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise LanHttpsError(f"openssl {' '.join(arguments[:2])} failed: {detail or 'unknown error'}")
    return result.stdout


def prepare_directories(paths: Paths) -> None:
    for directory in (paths.state, paths.ca_dir, paths.server_dir, paths.openssl_dir):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.suppress(OSError):
            directory.chmod(0o700)


def apply_permissions(paths: Paths) -> None:
    for private in (paths.ca_key, paths.server_key):
        if private.exists():
            with contextlib.suppress(OSError):
                private.chmod(0o600)
    for public in (
        paths.ca_cert,
        paths.ca_der,
        paths.server_cert,
        paths.server_csr,
        paths.server_chain,
        paths.server_ext,
        paths.state_json,
    ):
        if public.exists():
            with contextlib.suppress(OSError):
                public.chmod(0o644)


def validated_identities(ips: list[str], dns_names: list[str]) -> tuple[list[str], list[str]]:
    clean_ips: list[str] = []
    for raw in ips:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise LanHttpsError(f"invalid IP identity {raw!r}: {error}") from error
        if address.is_unspecified:
            raise LanHttpsError(f"{address} is a bind address, not a certificate identity")
        value = address.compressed
        if value not in clean_ips:
            clean_ips.append(value)

    clean_dns: list[str] = []
    for raw in dns_names:
        value = raw.strip().rstrip(".").lower()
        if not value or len(value) > 253 or ".." in value:
            raise LanHttpsError(f"invalid DNS identity: {raw!r}")
        labels = value.split(".")
        if any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise LanHttpsError(f"invalid DNS identity: {raw!r}")
        if value not in clean_dns:
            clean_dns.append(value)

    if not clean_ips and not clean_dns:
        raise LanHttpsError("provide at least one explicit --ip or --dns certificate identity")
    return clean_ips, clean_dns


def normalized_mount(raw: str) -> str:
    if not raw.startswith("/") or raw == "/" or "//" in raw or ".." in raw:
        raise LanHttpsError("--mount must be an absolute path such as /chrome")
    mount = raw.rstrip("/")
    if not re.fullmatch(r"/[A-Za-z0-9._~/-]+", mount):
        raise LanHttpsError(f"unsafe mount path: {raw!r}")
    return mount


def write_atomic(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def create_ca(paths: Paths) -> None:
    existing = [path for path in (paths.ca_key, paths.ca_cert, paths.ca_der) if path.exists()]
    if existing:
        if len(existing) == 3:
            return
        raise LanHttpsError("partial CA state exists; inspect it before replacing any root material")

    prepare_directories(paths)
    with tempfile.TemporaryDirectory(prefix="ca.", dir=paths.state) as temporary:
        work = Path(temporary)
        key = work / "root.key.pem"
        cert = work / "root.cert.pem"
        der = work / "root.cert.cer"
        run_openssl(
            "req", "-x509", "-new", "-nodes", "-newkey", "rsa:3072",
            "-keyout", str(key), "-out", str(cert), "-sha256", "-days", str(ROOT_DAYS),
            "-subj", "/CN=Chrome Web Labs Local Root CA",
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            "-addext", "subjectKeyIdentifier=hash",
        )
        run_openssl("x509", "-in", str(cert), "-outform", "DER", "-out", str(der))
        write_atomic(paths.ca_key, key.read_bytes(), 0o600)
        write_atomic(paths.ca_cert, cert.read_bytes(), 0o644)
        write_atomic(paths.ca_der, der.read_bytes(), 0o644)
    apply_permissions(paths)


def extension_text(ips: list[str], dns_names: list[str]) -> str:
    lines = [
        "[server]",
        "basicConstraints=critical,CA:FALSE",
        "keyUsage=critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage=serverAuth",
        "subjectKeyIdentifier=hash",
        "authorityKeyIdentifier=keyid,issuer",
        "subjectAltName=@alt_names",
        "",
        "[alt_names]",
    ]
    lines.extend(f"IP.{index}={value}" for index, value in enumerate(ips, 1))
    lines.extend(f"DNS.{index}={value}" for index, value in enumerate(dns_names, 1))
    return "\n".join(lines) + "\n"


def certificate_dict(path: Path) -> dict:
    try:
        return ssl._ssl._test_decode_cert(str(path))  # type: ignore[attr-defined]
    except (OSError, ssl.SSLError) as error:
        raise LanHttpsError(f"cannot decode certificate {path}: {error}") from error


def iso_certificate_time(value: str) -> str:
    timestamp = ssl.cert_time_to_seconds(value)
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def certificate_sans(path: Path) -> tuple[list[str], list[str]]:
    decoded = certificate_dict(path)
    ips: list[str] = []
    dns_names: list[str] = []
    for kind, value in decoded.get("subjectAltName", ()):
        if kind == "IP Address":
            ips.append(ipaddress.ip_address(value).compressed)
        elif kind == "DNS":
            dns_names.append(value.lower())
    return ips, dns_names


def certificate_fingerprint(path: Path) -> str:
    output = run_openssl("x509", "-in", str(path), "-noout", "-fingerprint", "-sha256")
    value = output.decode("ascii", "replace").strip().split("=", 1)[-1]
    return f"SHA256:{value.upper()}"


def certificate_serial(path: Path) -> str:
    output = run_openssl("x509", "-in", str(path), "-noout", "-serial")
    return output.decode("ascii", "replace").strip().split("=", 1)[-1]


def verify_certificate_chain(paths: Paths) -> None:
    run_openssl("verify", "-CAfile", str(paths.ca_cert), str(paths.server_cert))


def verify_ca(paths: Paths) -> None:
    run_openssl("verify", "-CAfile", str(paths.ca_cert), str(paths.ca_cert))
    if public_key_from_certificate(paths.ca_cert) != public_key_from_private_key(paths.ca_key):
        raise LanHttpsError("root CA certificate and private key do not match")
    text = run_openssl("x509", "-in", str(paths.ca_cert), "-noout", "-text")
    if b"CA:TRUE" not in text or b"Certificate Sign" not in text:
        raise LanHttpsError("root certificate lacks required CA/key-signing extensions")


def public_key_from_certificate(path: Path) -> bytes:
    return run_openssl("x509", "-in", str(path), "-pubkey", "-noout")


def public_key_from_private_key(path: Path) -> bytes:
    return run_openssl("pkey", "-in", str(path), "-pubout")


def verify_key_pairs(paths: Paths) -> None:
    if public_key_from_certificate(paths.ca_cert) != public_key_from_private_key(paths.ca_key):
        raise LanHttpsError("root CA certificate and private key do not match")
    if public_key_from_certificate(paths.server_cert) != public_key_from_private_key(paths.server_key):
        raise LanHttpsError("server certificate and private key do not match")


def write_state(paths: Paths, root: Path, port: int) -> dict:
    decoded = certificate_dict(paths.server_cert)
    ips, dns_names = certificate_sans(paths.server_cert)
    state = {
        "schemaVersion": SCHEMA_VERSION,
        "caFingerprint": certificate_fingerprint(paths.ca_cert),
        "certificateSerial": certificate_serial(paths.server_cert),
        "sanIps": ips,
        "sanDns": dns_names,
        "issuedAt": iso_certificate_time(decoded["notBefore"]),
        "expiresAt": iso_certificate_time(decoded["notAfter"]),
        "staticRoot": str(root.expanduser().resolve()),
        "expectedPort": port,
    }
    write_atomic(
        paths.state_json,
        (json.dumps(state, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )
    return state


def verify_key_material_permissions(path: Path) -> None:
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise LanHttpsError(f"private key permissions are too broad: {path} (expected mode 0600)")


def issue_leaf(paths: Paths, ips: list[str], dns_names: list[str], root: Path, port: int) -> dict:
    if not paths.ca_key.is_file() or not paths.ca_cert.is_file():
        raise LanHttpsError("private CA is missing; run init first")
    verify_key_material_permissions(paths.ca_key)
    prepare_directories(paths)
    common_name = dns_names[0] if dns_names else ips[0]
    extensions = extension_text(ips, dns_names).encode()

    with tempfile.TemporaryDirectory(prefix="leaf.", dir=paths.state) as temporary:
        work = Path(temporary)
        key = work / "server.key.pem"
        csr = work / "server.csr.pem"
        cert = work / "server.cert.pem"
        chain = work / "server-chain.pem"
        ext = work / "server.ext"
        ext.write_bytes(extensions)
        run_openssl(
            "req", "-new", "-nodes", "-newkey", "rsa:2048", "-keyout", str(key),
            "-out", str(csr), "-sha256", "-subj", f"/CN={common_name}",
        )
        serial = str(secrets.randbits(159) or 1)
        run_openssl(
            "x509", "-req", "-in", str(csr), "-CA", str(paths.ca_cert),
            "-CAkey", str(paths.ca_key), "-set_serial", serial, "-out", str(cert),
            "-days", str(LEAF_DAYS), "-sha256", "-extfile", str(ext), "-extensions", "server",
        )
        chain.write_bytes(cert.read_bytes() + paths.ca_cert.read_bytes())
        write_atomic(paths.server_key, key.read_bytes(), 0o600)
        write_atomic(paths.server_csr, csr.read_bytes(), 0o644)
        write_atomic(paths.server_cert, cert.read_bytes(), 0o644)
        write_atomic(paths.server_chain, chain.read_bytes(), 0o644)
        write_atomic(paths.server_ext, extensions, 0o644)

    apply_permissions(paths)
    verify_certificate_chain(paths)
    verify_key_pairs(paths)
    issued_ips, issued_dns = certificate_sans(paths.server_cert)
    if issued_ips != ips or issued_dns != dns_names:
        raise LanHttpsError(f"issued SANs differ from request: IP={issued_ips}, DNS={issued_dns}")
    return write_state(paths, root, port)


def existing_leaf_files(paths: Paths) -> list[Path]:
    return [
        path for path in (paths.server_key, paths.server_cert, paths.server_csr, paths.server_chain)
        if path.exists()
    ]


def command_init(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    ips, dns_names = validated_identities(args.ip, args.dns)
    ca_existed = paths.ca_cert.exists() and paths.ca_key.exists()
    create_ca(paths)
    existing = existing_leaf_files(paths)
    if existing:
        if len(existing) != 4:
            raise LanHttpsError("partial server certificate state exists; run clean after review")
        current_ips, current_dns = certificate_sans(paths.server_cert)
        if current_ips != ips or current_dns != dns_names:
            raise LanHttpsError("existing leaf has different SANs; use renew to preserve the trusted CA")
        state = write_state(paths, args.root, args.port)
        action = "preserved existing CA and matching leaf"
    else:
        state = issue_leaf(paths, ips, dns_names, args.root, args.port)
        action = "preserved existing CA and issued leaf" if ca_existed else "created CA and issued leaf"
    print_provisioned(paths, state, action)
    return 0


def command_issue(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    if existing_leaf_files(paths):
        raise LanHttpsError("server certificate state already exists; use renew to replace the leaf")
    ips, dns_names = validated_identities(args.ip, args.dns)
    state = issue_leaf(paths, ips, dns_names, args.root, args.port)
    print_provisioned(paths, state, "issued leaf using existing CA")
    return 0


def command_renew(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    ips, dns_names = validated_identities(args.ip, args.dns)
    before = paths.ca_cert.read_bytes() if paths.ca_cert.is_file() else None
    if before is None:
        raise LanHttpsError("private CA is missing; renewal cannot continue")
    state = issue_leaf(paths, ips, dns_names, args.root, args.port)
    if paths.ca_cert.read_bytes() != before:
        raise LanHttpsError("CA changed during leaf renewal")
    print_provisioned(paths, state, "renewed leaf; CA preserved")
    return 0


def print_provisioned(paths: Paths, state: dict, action: str) -> None:
    print(f"[lan-https][PASS] {action}")
    print(f"CA fingerprint: {state['caFingerprint']}")
    print(f"Leaf SAN IPs: {', '.join(state['sanIps']) or '(none)'}")
    print(f"Leaf SAN DNS: {', '.join(state['sanDns']) or '(none)'}")
    print(f"Leaf expires: {state['expiresAt']}")
    print(f"Trust this public certificate only: {paths.ca_der}")
    print(f"Never distribute: {paths.ca_key}")


def status_data(paths: Paths) -> dict:
    data: dict = {
        "schemaVersion": SCHEMA_VERSION,
        "stateDirectory": str(paths.state),
        "caExists": paths.ca_cert.is_file() and paths.ca_key.is_file(),
        "leafExists": paths.server_cert.is_file() and paths.server_key.is_file(),
    }
    if paths.ca_cert.is_file():
        data["caFingerprint"] = certificate_fingerprint(paths.ca_cert)
    if paths.server_cert.is_file():
        decoded = certificate_dict(paths.server_cert)
        ips, dns_names = certificate_sans(paths.server_cert)
        data.update(
            sanIps=ips,
            sanDns=dns_names,
            notBefore=iso_certificate_time(decoded["notBefore"]),
            notAfter=iso_certificate_time(decoded["notAfter"]),
            serial=certificate_serial(paths.server_cert),
        )
    if paths.state_json.is_file():
        try:
            data["state"] = json.loads(paths.state_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            data["stateError"] = str(error)
    return data


def command_status(args: argparse.Namespace) -> int:
    data = status_data(state_paths(args.state_dir))
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(f"State directory: {data['stateDirectory']}")
        print(f"CA exists: {data['caExists']}")
        if data.get("caFingerprint"):
            print(f"CA fingerprint: {data['caFingerprint']}")
        print(f"Leaf exists: {data['leafExists']}")
        if data.get("leafExists"):
            print(f"SAN IPs: {', '.join(data['sanIps']) or '(none)'}")
            print(f"SAN DNS: {', '.join(data['sanDns']) or '(none)'}")
            print(f"Not Before: {data['notBefore']}")
            print(f"Not After: {data['notAfter']}")
    return 0 if data["caExists"] and data["leafExists"] else 1


def command_fingerprint(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    if not paths.ca_cert.is_file():
        raise LanHttpsError("root CA certificate is missing; run init first")
    print(certificate_fingerprint(paths.ca_cert))
    return 0


class MountedStaticHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "ChromeLanHTTPS/1"

    def __init__(self, *arguments, directory: str, mount: str, quiet: bool = False, **keywords):
        self.mount = mount
        self.quiet = quiet
        super().__init__(*arguments, directory=directory, **keywords)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self.send_response(http.HTTPStatus.FOUND)
            self.send_header("Location", f"{self.mount}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path == self.mount:
            self.send_response(http.HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", f"{self.mount}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not parsed.path.startswith(f"{self.mount}/"):
            self.send_error(http.HTTPStatus.NOT_FOUND)
            return
        stripped = parsed.path[len(self.mount):] or "/"
        self.path = urlunsplit(("", "", stripped, parsed.query, parsed.fragment))
        super().do_GET()

    def log_message(self, format_: str, *arguments) -> None:
        if not self.quiet:
            super().log_message(format_, *arguments)


class ThreadingHTTPServerV6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


def create_https_server(
    bind: str,
    port: int,
    root: Path,
    mount: str,
    certificate: Path,
    key: Path,
    *,
    quiet: bool = False,
) -> http.server.ThreadingHTTPServer:
    if not root.is_dir() or not (root / "index.html").is_file():
        raise LanHttpsError(f"static root is missing index.html: {root}")
    handler = lambda *args, **kwargs: MountedStaticHandler(  # noqa: E731
        *args, directory=str(root), mount=mount, quiet=quiet, **kwargs
    )
    server_class = ThreadingHTTPServerV6 if ":" in bind else http.server.ThreadingHTTPServer
    try:
        server = server_class((bind, port), handler)
    except OSError as error:
        raise LanHttpsError(f"cannot bind {bind}:{port}: {error}") from error
    server.daemon_threads = True
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(str(certificate), str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
    except (OSError, ssl.SSLError) as error:
        server.server_close()
        raise LanHttpsError(f"cannot start TLS: {error}") from error
    return server


def ensure_server_material(paths: Paths) -> None:
    for path in (paths.ca_cert, paths.server_cert, paths.server_key):
        if not path.is_file():
            raise LanHttpsError(f"required HTTPS material is missing: {path}")
    verify_key_material_permissions(paths.server_key)
    verify_certificate_chain(paths)
    verify_key_pairs(paths)


def advertised_identities(paths: Paths, ips: list[str], dns_names: list[str]) -> tuple[list[str], list[str]]:
    if ips or dns_names:
        requested_ips, requested_dns = validated_identities(ips, dns_names)
    else:
        requested_ips, requested_dns = certificate_sans(paths.server_cert)
    certificate_ips, certificate_dns = certificate_sans(paths.server_cert)
    missing_ips = [value for value in requested_ips if value not in certificate_ips]
    missing_dns = [value for value in requested_dns if value not in certificate_dns]
    if missing_ips or missing_dns:
        raise LanHttpsError(
            f"certificate does not cover requested identities; missing IP={missing_ips}, DNS={missing_dns}; run renew"
        )
    return requested_ips, requested_dns


def display_host(value: str) -> str:
    return f"[{value}]" if ":" in value else value


def command_serve(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    root = args.root.expanduser().resolve()
    mount = normalized_mount(args.mount)
    ensure_server_material(paths)
    ips, dns_names = advertised_identities(paths, args.ip, args.dns)
    server = create_https_server(
        args.bind, args.port, root, mount, paths.server_chain, paths.server_key
    )
    actual_port = server.server_address[1]
    print(f"Static root: {root}")
    print(f"Bind: {args.bind}:{actual_port}")
    for identity in [*ips, *dns_names]:
        print(f"Test URL: https://{display_host(identity)}:{actual_port}{mount}/")
    print(f"CA fingerprint: {certificate_fingerprint(paths.ca_cert)}")
    print(f"Public CA certificate: {paths.ca_der}")
    decoded = certificate_dict(paths.server_cert)
    print(f"Certificate expires: {iso_certificate_time(decoded['notAfter'])}")
    print("No HTTP fallback is available. Press Ctrl-C to stop.")

    stopping = False

    def stop(_signum, _frame) -> None:
        nonlocal stopping
        if not stopping:
            stopping = True
            threading.Thread(target=server.shutdown, daemon=True).start()

    previous = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    print("[lan-https] stopped")
    return 0


def append_check(
    checks: list[Check], id_: str, status: str, message: str, remediation: str | None = None
) -> None:
    checks.append(Check(id_, status, message, remediation))


def validate_artifact(root: Path) -> list[str]:
    failures: list[str] = []
    if not root.is_dir():
        return [f"static root does not exist: {root}"]
    if not (root / "index.html").is_file():
        failures.append("root index.html is missing")
    publication = root / "meta" / "publication.json"
    checksums = root / "meta" / "checksums.sha256"
    if not publication.is_file():
        failures.append("meta/publication.json is missing")
    else:
        try:
            metadata = json.loads(publication.read_text(encoding="utf-8"))
            if not metadata.get("sourceSha"):
                failures.append("publication metadata has no sourceSha")
        except (OSError, json.JSONDecodeError) as error:
            failures.append(f"publication metadata is invalid: {error}")
    expected: dict[str, str] = {}
    if not checksums.is_file():
        failures.append("meta/checksums.sha256 is missing")
    else:
        for line in checksums.read_text(encoding="utf-8").splitlines():
            if not re.fullmatch(r"[0-9a-f]{64}  [^\r\n]+", line):
                failures.append("checksum manifest contains an invalid line")
                continue
            digest, relative = line.split("  ", 1)
            expected[relative] = digest
        for relative, digest in expected.items():
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                failures.append(f"checksum path escapes root: {relative}")
                continue
            if not candidate.is_file():
                failures.append(f"checksum target missing: {relative}")
            elif hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                failures.append(f"checksum mismatch: {relative}")
    for path in root.rglob("*"):
        if path.is_symlink():
            failures.append(f"artifact contains symlink: {path.relative_to(root)}")
        if path.is_file() and path.name.endswith((".key", ".key.pem")):
            failures.append(f"artifact contains private-key-like path: {path.relative_to(root)}")
        if path.is_file() and any(marker in path.read_bytes() for marker in PRIVATE_MARKERS):
            failures.append(f"artifact contains private-key material: {path.relative_to(root)}")
    return failures


def validity(path: Path, now: dt.datetime | None = None) -> tuple[str, str, float]:
    decoded = certificate_dict(path)
    current = now or dt.datetime.now(dt.timezone.utc)
    before = dt.datetime.fromtimestamp(ssl.cert_time_to_seconds(decoded["notBefore"]), dt.timezone.utc)
    after = dt.datetime.fromtimestamp(ssl.cert_time_to_seconds(decoded["notAfter"]), dt.timezone.utc)
    if current < before:
        raise LanHttpsError(f"certificate is not valid before {before.isoformat()}")
    if current > after:
        raise LanHttpsError(f"certificate expired at {after.isoformat()}")
    return before.isoformat(), after.isoformat(), (after - current).total_seconds() / 86400


def verified_fetch(
    server: http.server.ThreadingHTTPServer,
    connect_host: str,
    verify_identity: str,
    ca_cert: Path,
    mount: str,
) -> bytes:
    port = server.server_address[1]
    context = ssl.create_default_context(cafile=str(ca_cert))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((connect_host, port), timeout=5) as plain:
        with context.wrap_socket(plain, server_hostname=verify_identity) as secure:
            request_path = f"{mount}/index.html"
            request = (
                f"GET {request_path} HTTP/1.1\r\nHost: {verify_identity}\r\n"
                "Connection: close\r\n\r\n"
            )
            secure.sendall(request.encode("ascii"))
            response = http.client.HTTPResponse(secure)
            response.begin()
            body = response.read()
            if response.status != 200:
                raise LanHttpsError(f"HTTPS self-test returned HTTP {response.status}")
            return body


def command_doctor(args: argparse.Namespace) -> int:
    paths = state_paths(args.state_dir)
    root = args.root.expanduser().resolve()
    mount = normalized_mount(args.mount)
    checks: list[Check] = []
    data: dict = {
        "serverClock": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "stateDirectory": str(paths.state),
        "staticRoot": str(root),
        "mount": mount,
        "bind": args.bind,
        "port": args.port,
        "deviceTrustVerified": False,
    }

    append_check(checks, "python", "PASS", f"Python {sys.version.split()[0]} supported")
    try:
        executable = ensure_openssl()
        append_check(checks, "openssl", "PASS", f"OpenSSL available at {executable}")
    except LanHttpsError as error:
        append_check(checks, "openssl", "FAIL", str(error), "Install a local OpenSSL executable")

    ca_ready = paths.ca_cert.is_file() and paths.ca_key.is_file() and paths.ca_der.is_file()
    if ca_ready:
        append_check(checks, "ca-files", "PASS", "private CA files exist")
        try:
            verify_key_material_permissions(paths.ca_key)
            append_check(checks, "ca-key-permissions", "PASS", "CA private key permissions are restricted")
        except LanHttpsError as error:
            append_check(checks, "ca-key-permissions", "FAIL", str(error), f"chmod 600 {paths.ca_key}")
        try:
            verify_ca(paths)
            append_check(checks, "ca-integrity", "PASS", "CA is self-verifying and matches its private key")
        except LanHttpsError as error:
            append_check(checks, "ca-integrity", "FAIL", str(error), "Review CA state; do not replace it silently")
        try:
            fingerprint = certificate_fingerprint(paths.ca_cert)
            data["caFingerprint"] = fingerprint
            append_check(checks, "ca-fingerprint", "PASS", fingerprint)
            before, after, remaining = validity(paths.ca_cert)
            data["caNotBefore"] = before
            data["caNotAfter"] = after
            append_check(checks, "ca-validity", "PASS", f"CA valid for {remaining:.0f} more days")
        except LanHttpsError as error:
            append_check(checks, "ca-validity", "FAIL", str(error), "Review CA state; reset only with explicit approval")
    else:
        append_check(checks, "ca-files", "FAIL", "private CA state is incomplete or missing", "Run init with explicit --ip/--dns")

    leaf_ready = paths.server_cert.is_file() and paths.server_key.is_file()
    requested_ips: list[str] = []
    requested_dns: list[str] = []
    san_covered = False
    if leaf_ready:
        append_check(checks, "leaf-files", "PASS", "server certificate and private key exist")
        try:
            verify_key_material_permissions(paths.server_key)
            append_check(checks, "leaf-key-permissions", "PASS", "server private key permissions are restricted")
        except LanHttpsError as error:
            append_check(checks, "leaf-key-permissions", "FAIL", str(error), f"chmod 600 {paths.server_key}")
        try:
            verify_certificate_chain(paths)
            append_check(checks, "leaf-chain", "PASS", "server certificate verifies against the private CA")
        except LanHttpsError as error:
            append_check(checks, "leaf-chain", "FAIL", str(error), "Run renew using the existing CA")
        try:
            verify_key_pairs(paths)
            append_check(checks, "key-pairs", "PASS", "CA and leaf private keys match their certificates")
        except LanHttpsError as error:
            append_check(checks, "key-pairs", "FAIL", str(error), "Inspect state; do not replace the CA silently")
        try:
            certificate_ips, certificate_dns = certificate_sans(paths.server_cert)
            data["sanIps"] = certificate_ips
            data["sanDns"] = certificate_dns
            if args.ip or args.dns:
                requested_ips, requested_dns = validated_identities(args.ip, args.dns)
            else:
                requested_ips, requested_dns = certificate_ips, certificate_dns
            missing_ips = [value for value in requested_ips if value not in certificate_ips]
            missing_dns = [value for value in requested_dns if value not in certificate_dns]
            if missing_ips or missing_dns:
                append_check(
                    checks, "san-coverage", "FAIL",
                    f"certificate SAN omits IP={missing_ips}, DNS={missing_dns}",
                    "Run renew with every intended --ip and --dns identity",
                )
            else:
                san_covered = True
                append_check(checks, "san-coverage", "PASS", "certificate covers every requested identity")
            before, after, remaining = validity(paths.server_cert)
            data["certificateNotBefore"] = before
            data["certificateNotAfter"] = after
            status = "WARN" if remaining < EXPIRY_WARNING_DAYS else "PASS"
            remediation = "Run renew before expiration" if status == "WARN" else None
            append_check(checks, "leaf-validity", status, f"server certificate valid for {remaining:.1f} more days", remediation)
        except LanHttpsError as error:
            append_check(checks, "leaf-validity", "FAIL", str(error), "Run renew after checking the server clock")
    else:
        append_check(checks, "leaf-files", "FAIL", "server certificate state is missing", "Run issue or init")

    artifact_failures = validate_artifact(root)
    if artifact_failures:
        append_check(
            checks, "artifact", "FAIL", "; ".join(artifact_failures),
            "Build and validate the exact artifact with bash actions/www.pages.sh",
        )
    else:
        append_check(checks, "artifact", "PASS", "static artifact metadata, checksums, and files are valid")

    if ca_ready and leaf_ready and san_covered and not artifact_failures and requested_ips + requested_dns:
        identity = requested_ips[0] if requested_ips else requested_dns[0]
        connect_host = args.connect_host or identity
        server: http.server.ThreadingHTTPServer | None = None
        thread: threading.Thread | None = None
        try:
            server = create_https_server(
                args.bind, args.port, root, mount, paths.server_chain, paths.server_key, quiet=True
            )
            actual_port = server.server_address[1]
            data["selfTestUrl"] = f"https://{display_host(identity)}:{actual_port}{mount}/"
            append_check(checks, "bind", "PASS", f"HTTPS listener opened on {args.bind}:{actual_port}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            observed = verified_fetch(server, connect_host, identity, paths.ca_cert, mount)
            expected = (root / "index.html").read_bytes()
            if observed != expected:
                raise LanHttpsError("HTTPS response bytes differ from static index.html")
            append_check(checks, "https-self-test", "PASS", "verified TLS identity and exact static-file bytes")
        except (LanHttpsError, OSError, ssl.SSLError) as error:
            append_check(
                checks, "https-self-test", "FAIL", str(error),
                "Confirm the requested identity is local/reachable, the port is free, and then rerun doctor",
            )
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=2)
    else:
        append_check(checks, "https-self-test", "FAIL", "prerequisite CA, leaf, identity, or artifact check failed", "Fix earlier failures first")

    overall = "FAIL" if any(check.status == "FAIL" for check in checks) else "PASS"
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "overallStatus": overall,
        "checks": [asdict(check) for check in checks],
        "data": data,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"[{check.status}] {check.message}")
            if check.remediation and check.status != "PASS":
                print(f"       Fix: {check.remediation}")
        print("\nDEVICE ACTION REQUIRED:")
        print(f"Trust only: {paths.ca_der}")
        if data.get("caFingerprint"):
            print(f"Verify fingerprint: {data['caFingerprint']}")
        if data.get("selfTestUrl"):
            print(f"Then open: {data['selfTestUrl']}")
        print("Host diagnostics do not prove that a separate device trusts this CA.")
    return 0 if overall == "PASS" else 1


def command_clean(args: argparse.Namespace) -> int:
    if not args.yes:
        raise LanHttpsError("clean requires --yes; it removes only replaceable leaf state")
    paths = state_paths(args.state_dir)
    removed: list[str] = []
    for path in (
        paths.server_key, paths.server_cert, paths.server_csr,
        paths.server_chain, paths.server_ext, paths.state_json,
    ):
        if path.exists():
            path.unlink()
            removed.append(str(path))
    print(f"[lan-https][PASS] removed {len(removed)} leaf/state file(s); CA preserved")
    return 0


def command_reset_ca(args: argparse.Namespace) -> int:
    if args.confirm != "RESET-LAN-CA":
        raise LanHttpsError("reset-ca requires --confirm RESET-LAN-CA and explicit human authorization")
    ips, dns_names = validated_identities(args.ip, args.dns)
    paths = state_paths(args.state_dir)
    allowed = {
        paths.ca_dir,
        paths.server_dir,
        paths.openssl_dir,
        paths.ca_key,
        paths.ca_cert,
        paths.ca_der,
        paths.server_key,
        paths.server_cert,
        paths.server_csr,
        paths.server_chain,
        paths.server_ext,
        paths.state_json,
    }
    if paths.state.exists():
        observed = set(paths.state.rglob("*"))
        unexpected = sorted(str(path) for path in observed - allowed)
        if unexpected:
            raise LanHttpsError(
                "refusing to reset state with unexpected content: " + ", ".join(unexpected)
            )
        for generated in (
            paths.server_key, paths.server_cert, paths.server_csr, paths.server_chain,
            paths.server_ext, paths.state_json, paths.ca_der, paths.ca_cert, paths.ca_key,
        ):
            generated.unlink(missing_ok=True)
        for directory in (paths.server_dir, paths.openssl_dir, paths.ca_dir, paths.state):
            with contextlib.suppress(FileNotFoundError):
                directory.rmdir()
    create_ca(paths)
    state = issue_leaf(paths, ips, dns_names, args.root, args.port)
    print_provisioned(paths, state, "replaced CA and leaf; every device must trust the new public root")
    return 0


def add_state_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state-dir", type=Path,
        default=repository_root() / ".local" / "lan-https",
        help="generated local certificate state (default: .local/lan-https)",
    )


def add_identity_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ip", action="append", default=[], help="explicit IP SAN; repeatable")
    parser.add_argument("--dns", action="append", default=[], help="explicit DNS SAN; repeatable")


def add_artifact_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=repository_root() / "static")
    parser.add_argument("--port", type=int, default=8443)


def parser() -> argparse.ArgumentParser:
    root_parser = argparse.ArgumentParser(
        description="Trusted, offline-safe LAN HTTPS provisioning and static serving"
    )
    commands = root_parser.add_subparsers(dest="command", required=True)

    for name, handler in (("init", command_init), ("issue", command_issue), ("renew", command_renew)):
        command = commands.add_parser(name)
        add_state_option(command)
        add_identity_options(command)
        add_artifact_options(command)
        command.set_defaults(handler=handler)

    status = commands.add_parser("status")
    add_state_option(status)
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=command_status)

    fingerprint = commands.add_parser("fingerprint")
    add_state_option(fingerprint)
    fingerprint.set_defaults(handler=command_fingerprint)

    serve = commands.add_parser("serve")
    add_state_option(serve)
    add_identity_options(serve)
    add_artifact_options(serve)
    serve.add_argument("--bind", default="0.0.0.0")
    serve.add_argument("--mount", default="/chrome")
    serve.set_defaults(handler=command_serve)

    doctor = commands.add_parser("doctor")
    add_state_option(doctor)
    add_identity_options(doctor)
    add_artifact_options(doctor)
    doctor.add_argument("--bind", default="0.0.0.0")
    doctor.add_argument("--mount", default="/chrome")
    doctor.add_argument("--connect-host", help="socket destination while verifying the requested SAN identity")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=command_doctor)

    clean = commands.add_parser("clean")
    add_state_option(clean)
    clean.add_argument("--yes", action="store_true")
    clean.set_defaults(handler=command_clean)

    reset = commands.add_parser("reset-ca")
    add_state_option(reset)
    add_identity_options(reset)
    add_artifact_options(reset)
    reset.add_argument("--confirm")
    reset.set_defaults(handler=command_reset_ca)
    return root_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if hasattr(args, "port") and not 0 <= args.port <= 65535:
        raise LanHttpsError("--port must be between 0 and 65535")
    return args.handler(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LanHttpsError as error:
        print(f"[lan-https][FAIL] {error}", file=sys.stderr)
        raise SystemExit(1)
