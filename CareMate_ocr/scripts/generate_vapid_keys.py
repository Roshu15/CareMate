"""Create VAPID keys for browser push. Keep the private key secret and stable."""
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


private = ec.generate_private_key(ec.SECP256R1())
numbers = private.public_key().public_numbers()
public_bytes = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
private_pem = private.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode("ascii")

config = {
    "public_key": b64url(public_bytes),
    "private_key": private_pem,
}
output = Path(__file__).resolve().parents[1] / ".local_vapid_keys.json"
output.write_text(json.dumps(config, indent=2), encoding="utf-8")
print(f"VAPID keys saved to {output}. Keep the private key secret and do not commit this file.")
