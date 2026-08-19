# -*- coding: utf-8 -*-
"""Simple username/password auth -> persona mapping. No SSO required.

The point: the SERVER decides which persona(s) a user may use, based on who they
authenticated as — never trust a client-supplied `persona` field on its own once
auth is enabled. Storage is a small local JSON file (gitignored); passwords are
PBKDF2-hashed, never stored in plain text.

Manage users from the CLI:
  python auth.py add <username> <persona1,persona2,...>   # prompts for password
  python auth.py list
  python auth.py remove <username>
"""
import os
import sys
import json
import hmac
import hashlib
import getpass
import base64

import personas as _personas

_ITERATIONS = 200_000


def _users_path():
    return os.getenv("TAPESTRY_USERS_FILE",
                     os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json"))


def _load():
    p = _users_path()
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _save(users):
    with open(_users_path(), "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password, stored):
    try:
        _, iters, salt_b64, hash_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except Exception:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
    return hmac.compare_digest(dk, expected)


def authenticate(username, password):
    """Return {"username":..., "personas":[...]} on success, else None."""
    users = _load()
    rec = users.get(username)
    if not rec or not verify_password(password, rec.get("password_hash", "")):
        return None
    allowed = [p for p in rec.get("personas", []) if p in _personas.PERSONAS]
    if not allowed:
        return None
    return {"username": username, "personas": allowed}


def personas_for_identity(identity):
    """No-password lookup against the same users.json, for channels (e.g. Teams) that
    already authenticated the person themselves — we just need their permitted
    persona(s), not a second password. Case-insensitive/trimmed match on the username
    (set the username to the person's Teams display name when adding them for this).
    Returns the persona list, or None if the identity isn't a known user."""
    if not identity:
        return None
    target = identity.strip().lower()
    for username, rec in _load().items():
        if username.strip().lower() == target:
            allowed = [p for p in rec.get("personas", []) if p in _personas.PERSONAS]
            return allowed or None
    return None


def enabled():
    """Auth is only enforced if explicitly turned on AND at least one user exists —
    so a fresh/default deployment never silently locks itself out."""
    return os.getenv("TAPESTRY_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes") \
        and bool(_load())


# ---------------------------------------------------------------- CLI ------
def _cli_add(username, persona_csv):
    valid = set(_personas.PERSONAS)
    plist = [p.strip() for p in persona_csv.split(",") if p.strip()]
    bad = [p for p in plist if p not in valid]
    if bad:
        sys.exit(f"Unknown persona(s): {bad}. Valid: {sorted(valid)}")
    pw = getpass.getpass(f"Password for '{username}': ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        sys.exit("Passwords did not match.")
    users = _load()
    users[username] = {"password_hash": hash_password(pw), "personas": plist}
    _save(users)
    print(f"Added '{username}' -> personas {plist}  ({_users_path()})")


def _cli_list():
    users = _load()
    if not users:
        print(f"No users in {_users_path()}")
        return
    for u, rec in users.items():
        print(f"  {u:20s} -> {rec.get('personas')}")


def _cli_remove(username):
    users = _load()
    if username in users:
        del users[username]
        _save(users)
        print(f"Removed '{username}'.")
    else:
        print(f"No such user: {username}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) == 4:
        _cli_add(sys.argv[2], sys.argv[3])
    elif cmd == "list":
        _cli_list()
    elif cmd == "remove" and len(sys.argv) == 3:
        _cli_remove(sys.argv[2])
    else:
        sys.exit(__doc__)
