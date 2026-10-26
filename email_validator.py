import json
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import tarfile
import urllib.request
from typing import Tuple

BINARY_NAME = "check_if_email_exists"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(PROJECT_DIR, "bin")

RELEASE_URLS = {
    ("Darwin", "x86_64"): "https://github.com/reacherhq/check-if-email-exists/releases/download/v0.11.10/check_if_email_exists-x86_64-apple-darwin.tar.gz",
    ("Darwin", "arm64"): "https://github.com/reacherhq/check-if-email-exists/releases/download/v0.11.10/check_if_email_exists-x86_64-apple-darwin.tar.gz",
    ("Linux", "x86_64"): "https://github.com/reacherhq/check-if-email-exists/releases/download/v0.11.10/check_if_email_exists-x86_64-unknown-linux-gnu.tar.gz",
    ("Linux", "aarch64"): "https://github.com/reacherhq/check-if-email-exists/releases/download/v0.11.10/check_if_email_exists-aarch64-unknown-linux-gnu.tar.gz",
}

# Cached port 25 reachability flag (None = unchecked)
_PORT_25_ACCESSIBLE = None

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def is_port_25_open() -> bool:
    """Check once if outbound port 25 is accessible from the current environment."""
    global _PORT_25_ACCESSIBLE
    if _PORT_25_ACCESSIBLE is not None:
        return _PORT_25_ACCESSIBLE

    try:
        # Quick 1.5-second socket probe to Google's public MX server
        sock = socket.create_connection(("gmail-smtp-in.l.google.com", 25), timeout=1.5)
        sock.close()
        _PORT_25_ACCESSIBLE = True
    except Exception:
        _PORT_25_ACCESSIBLE = False

    return _PORT_25_ACCESSIBLE


def check_domain_has_mx(domain: str) -> bool:
    """Fallback DNS MX check using nslookup (fast, no external dependencies)."""
    try:
        proc = subprocess.run(
            ["nslookup", "-type=mx", domain],
            capture_output=True,
            text=True,
            timeout=3
        )
        stdout = proc.stdout.lower()
        if "mail exchanger" in stdout:
            return True
        if "server can't find" in stdout or "non-existent domain" in stdout:
            return False
        # If no explicit MX line found, fallback to checking A record
        return bool(proc.returncode == 0)
    except Exception:
        # On lookup failure, don't falsely reject
        return True


def get_checker_binary() -> str:
    """Ensure check_if_email_exists binary is available, downloading if needed."""
    sys_path = shutil.which(BINARY_NAME)
    if sys_path and os.access(sys_path, os.X_OK):
        return sys_path

    local_path = os.path.join(BIN_DIR, BINARY_NAME)
    if os.path.exists(local_path) and os.access(local_path, os.X_OK):
        return local_path

    os.makedirs(BIN_DIR, exist_ok=True)
    system = platform.system()
    machine = platform.machine()
    url = RELEASE_URLS.get((system, machine))

    if not url:
        if system == "Linux":
            url = RELEASE_URLS[("Linux", "x86_64")]
        elif system == "Darwin":
            url = RELEASE_URLS[("Darwin", "x86_64")]
        else:
            raise RuntimeError(f"Unsupported OS/architecture for {BINARY_NAME}: {system} {machine}")

    print(f"📥 Downloading {BINARY_NAME} from {url}...")
    tar_path = os.path.join(BIN_DIR, f"{BINARY_NAME}.tar.gz")
    urllib.request.urlretrieve(url, tar_path)

    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(path=BIN_DIR)

    if os.path.exists(tar_path):
        os.remove(tar_path)

    os.chmod(local_path, os.stat(local_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    print(f"✅ {BINARY_NAME} installed to {local_path}")
    return local_path


def verify_email(to_email: str, sender_email: str = None) -> Tuple[bool, str]:
    """Verify email validity using reacherhq/check-if-email-exists with smart environment fallback.

    Returns:
        (is_valid, reason):
            is_valid = True if reachable / deliverable / safe / risky
            is_valid = False if invalid / unreachable / bounce
    """
    to_email = str(to_email).strip()
    if not to_email or not EMAIL_REGEX.match(to_email):
        return False, "Malformed or invalid email syntax"

    domain = to_email.split("@")[-1].strip().lower()

    # If outbound port 25 is blocked (e.g., inside GitHub Actions runners or restricted networks)
    if not is_port_25_open():
        # Avoid the slow 2.5-minute timeout. Perform instant DNS MX lookup
        if not check_domain_has_mx(domain):
            return False, f"Domain '{domain}' does not have active MX mail servers (bounces)"
        return True, "Valid syntax and MX records (port 25 blocked in runner, skipped deep SMTP probe)"

    # If port 25 is open (e.g. running locally on Mac or unblocked server), run reacherhq CLI
    try:
        binary_path = get_checker_binary()
        cmd = [binary_path]
        if sender_email and sender_email.strip():
            cmd.extend(["--from-email", sender_email.strip()])
        cmd.append(to_email)

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode != 0:
            print(f"⚠️  check_if_email_exists exited with code {proc.returncode}: {proc.stderr.strip()}")
            return True, f"Checker warning: {proc.stderr.strip()}"

        data = json.loads(proc.stdout)
        is_reachable = str(data.get("is_reachable", "")).lower()

        # Syntax check
        syntax = data.get("syntax", {})
        if not syntax.get("is_valid_syntax", True):
            return False, "Invalid email syntax"

        # MX records check
        mx = data.get("mx", {})
        if not mx.get("accepts_mail", True):
            return False, "Domain does not accept mail (no MX records)"

        # Mailbox disabled check
        smtp = data.get("smtp", {})
        if smtp.get("is_disabled", False):
            return False, "Mailbox is disabled"

        # Explicitly rejected recipient
        if is_reachable == "invalid":
            return False, "Recipient address is invalid / unreachable (bounces)"

        return True, f"Reachable ({is_reachable})"

    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout verifying {to_email}, proceeding with caution")
        return True, "Verification timed out"
    except Exception as e:
        print(f"⚠️  Error during email verification of {to_email}: {e}")
        return True, f"Verification skipped due to error: {e}"


if __name__ == "__main__":
    import sys
    test = sys.argv[1] if len(sys.argv) > 1 else "priyanshukhandelwal89@gmail.com"
    valid, reason = verify_email(test)
    print(f"Port 25 open: {is_port_25_open()}")
    print(f"Email: {test}\nValid: {valid}\nReason: {reason}")
