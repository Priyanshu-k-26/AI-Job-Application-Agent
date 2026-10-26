import json
import os
import platform
import shutil
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


def get_checker_binary() -> str:
    """Ensure check_if_email_exists binary is available, downloading if needed."""
    # 1. System PATH
    sys_path = shutil.which(BINARY_NAME)
    if sys_path and os.access(sys_path, os.X_OK):
        return sys_path

    # 2. Local project bin directory
    local_path = os.path.join(BIN_DIR, BINARY_NAME)
    if os.path.exists(local_path) and os.access(local_path, os.X_OK):
        return local_path

    # 3. Auto-download from GitHub releases
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
    """Verify email validity using reacherhq/check-if-email-exists.

    Returns:
        (is_valid, reason):
            is_valid = True if reachable / deliverable / safe / risky
            is_valid = False if invalid / unreachable / bounce
    """
    to_email = str(to_email).strip()
    if not to_email or "@" not in to_email:
        return False, "Malformed or empty email address"

    try:
        binary_path = get_checker_binary()
        cmd = [binary_path]
        if sender_email and sender_email.strip():
            cmd.extend(["--from-email", sender_email.strip()])
        cmd.append(to_email)

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
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

        # Unreachable / invalid recipient
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
    email_to_test = sys.argv[1] if len(sys.argv) > 1 else "priyanshukhandelwal89@gmail.com"
    valid, reason = verify_email(email_to_test)
    print(f"Email: {email_to_test}\nValid: {valid}\nReason: {reason}")
