"""Paired remote TVs for the public recommendation listener.

One private JSON file (mode 600) is the only record of which device may see which profiles.
Tokens and pairing codes are stored only as SHA-256 hashes; the plaintext token is returned once,
to the TV, by pair(). Source IP is never part of device authorization.
"""
import fcntl, hashlib, hmac, json, os, re, secrets, tempfile, time
from contextlib import contextmanager
from pathlib import Path

CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # no 0/O, 1/I/L
CODE_LENGTH = 8
CODE_TTL = 15*60
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}')
PROFILE = re.compile(r'household|ftv-netflix-[a-f0-9]{16}')


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def normalize_code(code):
    if not isinstance(code, str):
        return ''
    code = re.sub(r'[\s-]', '', code).upper()
    return code if len(code) == CODE_LENGTH and all(c in CODE_ALPHABET for c in code) else ''


class DeviceError(ValueError):
    pass


class RegistryUnreadable(DeviceError):
    pass


class DeviceRegistry:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name+'.lock')
        fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read(self):
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {'schema': 1, 'devices': []}
        except (OSError, ValueError):
            raise RegistryUnreadable('Device registry is unreadable')
        if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('devices'), list):
            raise RegistryUnreadable('Device registry is unreadable')
        return data

    def write(self, data):
        with tempfile.NamedTemporaryFile('w', dir=self.path.parent, prefix='.devices-', delete=False) as out:
            tmp = Path(out.name)
            try:
                os.chmod(tmp, 0o600)
                json.dump(data, out, indent=1)
                out.close()
                tmp.replace(self.path)
            finally:
                tmp.unlink(missing_ok=True)

    # Owner operations (pair_device.py on the Mac) ---------------------------------------------

    def create(self, label, profiles, replace=False):
        """Start pairing: returns the one-time code (shown once to the owner)."""
        if not isinstance(label, str) or not LABEL.fullmatch(label):
            raise DeviceError('Label: 1-40 letters, digits, space, dot, dash or underscore')
        if not profiles or not all(isinstance(p, str) and PROFILE.fullmatch(p) for p in profiles):
            raise DeviceError('Choose at least one valid profile')
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        now = self.clock()
        with self.locked():
            data = self.read()
            device = next((d for d in data['devices'] if d['label'].lower() == label.lower()), None)
            if device and not device['revoked'] and not replace:
                raise DeviceError('A device with this label exists; use --replace or --revoke')
            if device is None:
                device = {'id': 'dev-'+secrets.token_hex(6), 'label': label}
                data['devices'].append(device)
            # A new code always invalidates the device's previous token.
            device.update(profiles=sorted(set(profiles)), created=int(now), revoked=False, tokenSha256=None,
                          code={'sha256': digest(code), 'expires': int(now+CODE_TTL)})
            self.write(data)
        return code

    def revoke(self, label):
        with self.locked():
            data = self.read()
            device = next((d for d in data['devices'] if d['label'].lower() == label.lower()), None)
            if device is None:
                raise DeviceError('No device with this label')
            device.update(revoked=True, code=None)  # keep tokenSha256 so the TV learns it was removed
            self.write(data)

    def summary(self):
        now = self.clock()
        out = []
        for d in self.read()['devices']:
            status = ('revoked' if d['revoked'] else 'paired' if d.get('tokenSha256')
                      else 'code pending' if d.get('code') and d['code']['expires'] > now else 'code expired')
            out.append({'label': d['label'], 'profiles': list(d['profiles']), 'status': status, 'created': d['created']})
        return out

    # TV operations (public listener) ---------------------------------------------------------

    def pair(self, code):
        """Exchange a one-time code for a device token. Returns (token, device) or raises."""
        code = normalize_code(code)
        if not code:
            raise DeviceError('Pairing code is wrong or expired')
        hashed = digest(code)
        now = self.clock()
        with self.locked():
            data = self.read()
            for device in data['devices']:
                pending = device.get('code')
                if (pending and not device['revoked'] and pending['expires'] > now
                        and hmac.compare_digest(pending['sha256'], hashed)):
                    token = secrets.token_urlsafe(32)
                    device.update(tokenSha256=digest(token), code=None, paired=int(now))
                    self.write(data)
                    return token, self.public(device)
        raise DeviceError('Pairing code is wrong or expired')

    def authenticate(self, header):
        """Bearer header -> ('ok', device) | ('revoked', None) | ('unknown', None)."""
        if not isinstance(header, str) or not header.startswith('Bearer '):
            return 'unknown', None
        token = header[7:].strip()
        if not 20 <= len(token) <= 200:
            return 'unknown', None
        hashed = digest(token)
        for device in self.read()['devices']:
            stored = device.get('tokenSha256')
            if stored and hmac.compare_digest(stored, hashed):
                return ('revoked', None) if device['revoked'] else ('ok', self.public(device))
        return 'unknown', None

    @staticmethod
    def public(device):
        return {'id': device['id'], 'label': device['label'], 'profiles': list(device['profiles'])}
