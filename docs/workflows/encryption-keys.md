# Encryption keys: adding a new key and retiring an old one (spec 13.3; HIMS-SEC-011)

HIMS encrypts the secrets it must read back: authenticator app secrets (two-factor) and the real
text of messages not yet delivered. The keys are in the setting `HIMS_FIELD_ENCRYPTION_KEYS`, a
list of keys, **newest first**. New values use the first key; any key in the list can read a value.
On a developer PC with no keys set, a key derived from `DJANGO_SECRET_KEY` is used.

## When to rotate

Once a year, whenever someone who knew a key leaves, and at once if a key may have leaked.

## Steps (CMD, in `backend`, venv active)

1. Make a new key:
   ```
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Put it **first** in `HIMS_FIELD_ENCRYPTION_KEYS`, keeping the old key after it (comma
   separated), in the environment's secret store (or `.env` on a PC). Restart HIMS (web and
   workers).
3. See what still needs the old key, then encrypt everything again with the new key:
   ```
   python manage.py rotate_encryption_keys --dry-run
   python manage.py rotate_encryption_keys
   ```
   The last line must say `Values still needing an older key: 0.` The run is recorded in the
   audit log ("Stored secrets encrypted again with the newest key").
4. Check **Compliance → Security review → Encryption keys** (or **Security status** in the console):
   "every stored secret uses the newest key".
5. Remove the old key from the list and restart. Keep a copy of it, locked away, until every
   backup made before step 3 has expired: restoring such a backup needs the old key.

Running the command again is harmless (it finds nothing to change). If a value cannot be read
with any listed key, the command stops and changes nothing: a key was removed too early.
