"""Inspect persisted SDK/system key files without emitting private-key material."""

import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import subprocess


ROOTS = tuple(Path(path) for path in ("/root", "/home", "/cache", "/workspace", "/tmp",
                                    "/opt", "/usr", "/etc", "/var"))
STORE_SUFFIXES = {".pfx", ".p12", ".jks", ".keystore"}
KEY_SUFFIXES = {".key", ".priv", ".pk8", ".p8"}
CERT_SUFFIXES = {".pem", ".crt", ".cer", ".der"}
SOURCE_SUFFIXES = {".dart", ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".kts",
                   ".c", ".cc", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".sh", ".bash",
                   ".json", ".yaml", ".yml", ".toml", ".xml", ".txt", ".md", ".cfg", ".conf",
                   ".ini", ".properties"}
SOURCE_MAX_BYTES = 2 * 1024 * 1024
CREDENTIAL_NAMES = {".git-credentials", "credentials", "credentials.json", ".netrc",
                    "key.properties", "google-services.json", ".npmrc"}
SSH_KEY_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
PRIVATE_PEM = re.compile(rb"^-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----\r?$", re.MULTILINE)
EMBEDDED_PEM = re.compile(rb"-----BEGIN ((?:[A-Z0-9]+ )*PRIVATE KEY)-----")


def has_embedded_private_pem(data):
    # Handle both raw multiline literals and JSON/string escaped newlines.
    data = data.replace(b"\\r\\n", b"\n").replace(b"\\n", b"\n")
    for begin in EMBEDDED_PEM.finditer(data):
        end = data.find(b"-----END " + begin.group(1) + b"-----", begin.end())
        if end != -1 and re.search(rb"(?:^|[\r\n])[ \t]*[A-Za-z0-9+/]{32,}={0,2}[ \t]*(?:[\r\n]|$)",
                                   data[begin.end():end]):
            return True
    return False  # A quoted header constant without PEM payload is not a key.


def openssl(*args):
    # Every invocation suppresses key output. Never include stderr/content in evidence.
    result = subprocess.run(["openssl", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=30, check=False)
    return result.returncode, result.stdout + result.stderr


def jks_has_key(data):
    """Parse JKS/JCEKS entry types, not encrypted private/secret key contents."""
    offset = 0

    def take(size):
        nonlocal offset
        if size < 0 or offset + size > len(data):
            raise ValueError("Truncated Java store")
        value = data[offset:offset + size]
        offset += size
        return value

    def integer():
        return struct.unpack(">I", take(4))[0]

    def utf():
        return take(struct.unpack(">H", take(2))[0])

    magic, version, count = integer(), integer(), integer()
    if magic not in (0xFEEDFEED, 0xCECECECE) or version not in (1, 2):
        raise ValueError("Unknown Java store format")
    for _ in range(count):
        tag = integer()
        if tag == 1 or (magic == 0xCECECECE and tag == 3):
            return True
        if tag != 2:
            raise ValueError("Unknown Java store entry")
        utf()  # Alias is not reported.
        take(8)  # Timestamp.
        if version == 2 and utf() not in (b"X.509", b"X509"):
            raise ValueError("Unexpected trusted-certificate type")
        certificate = take(integer())
        # Certificate entries are checked as DER X.509, not trusted by filename.
        parsed = subprocess.run(["openssl", "x509", "-inform", "DER", "-noout"],
                                input=certificate, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=30, check=False)
        if parsed.returncode:
            raise ValueError("Invalid trusted certificate")
    if len(take(20)) != 20 or offset != len(data):
        raise ValueError("Unexpected Java store trailer")
    return False


def classify_key_file(path):
    """Return a key finding or None for a verified certificate-only/public-key file."""
    with path.open("rb") as source:
        prefix = source.read(4)
    suffix = path.suffix.lower()
    if prefix in (b"\xfe\xed\xfe\xed", b"\xce\xce\xce\xce"):
        if path.stat().st_size > 64 * 1024 * 1024:
            return "uninspectable Java key store (size limit)"
        try:
            return "Java private/secret-key entry" if jks_has_key(path.read_bytes()) else None
        except ValueError:
            return "uninspectable Java key store"
    if suffix in STORE_SUFFIXES or (path.name.lower() in {"cacerts", "jssecacerts"}
                                   and prefix.startswith(b"\x30")):
        # Empty and documented Java/Android debug defaults only. Opaque stores
        # fail closed; no arbitrary password guessing or key export is performed.
        for password in ("", "changeit", "android"):
            code, information = openssl("pkcs12", "-in", str(path), "-info", "-noout", "-nokeys",
                                        "-nocerts", "-passin", "pass:" + password, "-legacy")
            if code == 0:
                return "PKCS#12 private-key bag" if re.search(rb"\b(?:Shrouded Keybag|Keybag|Key bag)\b", information, re.I) else None
        return "uninspectable key store"

    # PEM bundles can put a private key after many certificates. Scan the entire
    # candidate, not just a prefix, but retain only enough overlap for a header.
    with path.open("rb") as source:
        previous = b""
        while chunk := source.read(65536):
            if PRIVATE_PEM.search(previous + chunk):
                return "PEM private-key material"
            previous = chunk[-128:]
    code, _ = openssl("pkey", "-inform", "DER", "-in", str(path), "-noout", "-passin", "pass:")
    if code == 0:
        return "DER private-key material"
    for form in ("PEM", "DER"):
        if openssl("x509", "-inform", form, "-in", str(path), "-noout")[0] == 0:
            return None
        if openssl("pkey", "-pubin", "-inform", form, "-in", str(path), "-noout")[0] == 0:
            return None
    if (suffix in KEY_SUFFIXES | CERT_SUFFIXES or path.name in SSH_KEY_NAMES
            or (path.name.startswith("ssh_host_") and path.name.endswith("_key"))):
        return "uninspectable key/certificate file"
    return None  # Plain configuration named cacerts is not a binary key store.


def inspect_credentials(roots=ROOTS):
    findings, inspected = [], 0
    source_inspected, source_over_limit = 0, 0

    def fail_walk(error):
        raise error  # An unreadable subtree must not silently pass qualification.

    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for directory, _directories, names in os.walk(root, followlinks=False, onerror=fail_walk):
            for name in names:
                path = Path(directory) / name
                suffix = path.suffix.lower()
                credential = name in CREDENTIAL_NAMES
                candidate = (credential or suffix in STORE_SUFFIXES | KEY_SUFFIXES | CERT_SUFFIXES
                             or name in SSH_KEY_NAMES or name.lower() in {"cacerts", "jssecacerts"}
                             or (name.startswith("ssh_host_") and name.endswith("_key")))
                source_candidate = suffix in SOURCE_SUFFIXES
                if not candidate and not source_candidate:
                    continue
                if path.is_symlink() and not path.exists():
                    continue  # A dangling link contains no key bytes to inspect.
                file_stat = path.stat()  # Resolve individual certificate links, not directory links.
                if not stat.S_ISREG(file_stat.st_mode):
                    continue
                if not candidate:
                    if file_stat.st_size > SOURCE_MAX_BYTES:
                        source_over_limit += 1
                        continue
                    inspection_class = ("bounded-source-pem",)
                elif credential:
                    # Sensitive names are path-policy findings, even when the
                    # inode was already accepted under a harmless alias.
                    inspection_class = ("credential-name", str(path))
                elif suffix in STORE_SUFFIXES:
                    inspection_class = ("key-store",)
                elif name.lower() in {"cacerts", "jssecacerts"}:
                    inspection_class = ("named-trust-store",)
                else:
                    inspection_class = ("key-material",)
                identity = (file_stat.st_dev, file_stat.st_ino, inspection_class)
                if identity in seen:
                    continue
                if not candidate:
                    source_inspected += 1
                    reason = "embedded PEM private-key material" if has_embedded_private_pem(path.read_bytes()) else None
                else:
                    reason = "credential configuration file" if credential else classify_key_file(path)
                inspected += 1
                if reason:
                    with path.open("rb") as source:
                        digest = hashlib.file_digest(source, "sha256").hexdigest()
                    findings.append({"path": str(path), "reason": reason, "sha256": digest})
                seen.add(identity)  # Only completed, equivalent inspections deduplicate.
    return {"findings": sorted(findings, key=lambda f: f["path"]), "candidate_files_inspected": inspected,
            "roots": [str(root) for root in roots],
            "source_files_inspected": source_inspected, "source_files_over_limit": source_over_limit,
            "source_file_limit_bytes": SOURCE_MAX_BYTES, "source_suffixes": sorted(SOURCE_SUFFIXES),
            "limitation": "key/config files and bounded source PEM blocks; not all-layer, oversized source or arbitrary encoded-secret scanning"}
