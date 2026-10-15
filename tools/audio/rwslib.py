"""RenderWare Audio (RWA 3.x, PS2) wave dictionary (.RWS) + Milestone .CRW sidecar library.

MotoGP 08 (SLUS-21811). All multi-byte values little endian.

.RWS layout (every chunk = u32 id, u32 payload size, u32 version 0x1c020037, payload):
  0x809 WaveDict            payload = 0x80a chunk + 0x80c chunk
    0x80a DictHeader        0x44 bytes: 36 bytes of tool-side pointer garbage (ignored),
                            16-byte dict UUID, 16-byte NUL-padded dict name ("Collision")
    0x80c WaveList          u32 wave count, then <count> 0x802 chunks
      0x802 Wave            payload = 0x803 chunk + 0x804 chunk
        0x803 WaveHeader    +0x00 u32  0x0000000f (constant in every bank)
                            +0x04 fmt A (44 bytes)  +0x30 fmt B (44 bytes), same layout:
                                  +0  u32 sample rate (Hz)       +4  u32 garbage ptr
                                  +8  u32 data size in bytes     +12 u8 bits/sample (4)
                                  +13 u8 channels (1)            +14 u16 garbage
                                  +16 12 bytes (0 / garbage)     +28 16-byte codec UUID
                                  (codec UUID 9897ead9bcbb7b4496b2654759102e16 = PS2 VAG ADPCM)
                            +0x5c u32  1 = positional (3D voice), 0 = 2D voice (pan control)
                            +0x60 16-byte wave UUID (unique per wave)
                            +0x70 wave name, NUL terminated, padded to a multiple of 16
                                  (pad bytes are tool garbage)
                            +end-32 32 bytes: two UUIDs, identical in every wave of every bank
        0x804 WaveData      raw PS-ADPCM (SPU2 "VAG" body without header), 16-byte frames,
                            every frame has flag byte 0x02 (RWA handles the end itself)

.CRW (text, CRLF): "TXT1", count, then <count> blocks
  category      N        (0 MUSIC, 1 SFX, 2 MENU, 3 ENVIRONMENT, 4 ENGINE, 5 EFFECTS - the
                          MasterVolume order in SFX\\AudioConfig.xml)
  name      X
  attenuator      F      (linear gain multiplied into the voice volume)
  EndStruct
Block i applies to wave i of the .RWS with the same base name. The count MUST equal the
.RWS wave count (the game indexes the sound list with it without a bound check).
"""
import os
import struct
import uuid as _uuid

VER = 0x1C020037
ID_DICT, ID_DHDR, ID_LIST, ID_WAVE, ID_WHDR, ID_WDATA = 0x809, 0x80A, 0x80C, 0x802, 0x803, 0x804
VAG_UUID = bytes.fromhex('9897ead9bcbb7b4496b2654759102e16')

# ----------------------------------------------------------------------------- PS-ADPCM
COEF = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]


def adpcm_decode(data):
    """PS-ADPCM -> list of int16 samples (mono)."""
    out = []
    h1 = h2 = 0
    for o in range(0, len(data) - 15, 16):
        sf = data[o]
        shift, filt = sf & 0x0F, (sf >> 4) & 0x0F
        if filt > 4:
            filt = 0
        k0, k1 = COEF[filt]
        for i in range(28):
            b = data[o + 2 + (i >> 1)]
            n = (b >> 4) if (i & 1) else (b & 0x0F)
            if n >= 8:
                n -= 16
            s = (n << 12) >> shift if shift <= 12 else 0
            s += (h1 * k0 + h2 * k1 + 32) >> 6
            s = max(-32768, min(32767, s))
            out.append(s)
            h2, h1 = h1, s
    return out


def adpcm_encode(samples, flag=0x02, pad_silent_frame=True):
    """int16 samples -> PS-ADPCM bytes. Closed-loop search over the 5 filters and the shift
    range, keeping the encoder history equal to the decoder's. Every frame gets `flag`
    (0x02, like the game's banks). A trailing silent frame (0c 02 00..) is appended, as most
    of the stock banks end with one."""
    import numpy as np
    x = np.asarray(samples, dtype=np.int64)
    if len(x) % 28:
        x = np.concatenate([x, np.zeros(28 - len(x) % 28, dtype=np.int64)])
    out = bytearray()
    h1 = h2 = 0
    for f0 in range(0, len(x), 28):
        blk = x[f0:f0 + 28]
        best = None
        for filt, (k0, k1) in enumerate(COEF):
            # open-loop residual estimate to choose the shift
            p1, p2, peak = h1, h2, 0
            for s in blk:
                r = int(s) - ((p1 * k0 + p2 * k1 + 32) >> 6)
                peak = max(peak, abs(r))
                p2, p1 = p1, int(s)
            sh = 12
            while sh > 0 and peak > 7 * (1 << (12 - sh)):
                sh -= 1
            for shift in sorted({sh, max(0, sh - 1), min(12, sh + 1)}):
                p1, p2, err, nib = h1, h2, 0, []
                scale = 1 << (12 - shift)
                for s in blk:
                    pred = (p1 * k0 + p2 * k1 + 32) >> 6
                    r = int(s) - pred
                    n = int(round(r / scale))
                    n = max(-8, min(7, n))
                    d = ((n << 12) >> shift) + pred
                    d = max(-32768, min(32767, d))
                    err += (int(s) - d) ** 2
                    nib.append(n & 0xF)
                    p2, p1 = p1, d
                if best is None or err < best[0]:
                    best = (err, filt, shift, nib, p1, p2)
        _, filt, shift, nib, h1, h2 = best
        fr = bytearray(16)
        fr[0] = (filt << 4) | shift
        fr[1] = flag
        for i in range(14):
            fr[2 + i] = nib[2 * i] | (nib[2 * i + 1] << 4)
        out += fr
    if pad_silent_frame:
        out += bytes([0x0C, flag]) + bytes(14)
    return bytes(out)


# ----------------------------------------------------------------------------- WAV
def read_wav(path):
    """-> (rate, list[int16] mono). PCM 8/16/24/32-bit and float32; stereo is averaged."""
    import numpy as np
    d = open(path, 'rb').read()
    if d[:4] != b'RIFF' or d[8:12] != b'WAVE':
        raise ValueError('not a RIFF/WAVE file: %s' % path)
    o, fmt, data = 12, None, None
    while o + 8 <= len(d):
        cid, sz = d[o:o + 4], struct.unpack_from('<I', d, o + 4)[0]
        if cid == b'fmt ':
            fmt = struct.unpack_from('<HHIIHH', d, o + 8)
        elif cid == b'data':
            data = d[o + 8:o + 8 + sz]
        o += 8 + sz + (sz & 1)
    tag, ch, rate, _, align, bits = fmt
    if tag == 0xFFFE:
        tag = struct.unpack_from('<H', d, d.find(b'fmt ') + 8 + 24)[0]
    n = len(data) // align
    if tag == 3 and bits == 32:
        a = np.frombuffer(data[:n * align], '<f4').reshape(n, ch) * 32767.0
    elif tag == 1 and bits == 16:
        a = np.frombuffer(data[:n * align], '<i2').reshape(n, ch).astype(np.float64)
    elif tag == 1 and bits == 8:
        a = (np.frombuffer(data[:n * align], 'u1').reshape(n, ch).astype(np.float64) - 128) * 256
    elif tag == 1 and bits == 24:
        b = np.frombuffer(data[:n * align], 'u1').reshape(n, ch, 3).astype(np.int32)
        v = b[..., 0] | (b[..., 1] << 8) | (b[..., 2] << 16)
        v = np.where(v >= 1 << 23, v - (1 << 24), v)
        a = v.astype(np.float64) / 256
    elif tag == 1 and bits == 32:
        a = np.frombuffer(data[:n * align], '<i4').reshape(n, ch).astype(np.float64) / 65536
    else:
        raise ValueError('unsupported WAV format tag=%d bits=%d' % (tag, bits))
    m = a.mean(axis=1)
    return rate, m


def resample(x, src, dst):
    import numpy as np
    x = np.asarray(x, dtype=np.float64)
    if src == dst:
        return x
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(src, dst)
        return resample_poly(x, dst // g, src // g)
    except ImportError:
        n = int(round(len(x) * dst / src))
        return np.interp(np.arange(n) * src / dst, np.arange(len(x)), x)


def to_int16(x, normalize_peak=None):
    import numpy as np
    x = np.asarray(x, dtype=np.float64)
    if normalize_peak:
        pk = np.max(np.abs(x)) or 1.0
        x = x * (normalize_peak * 32767.0 / pk)
    return np.clip(np.round(x), -32768, 32767).astype(np.int64)


def write_wav(path, rate, samples):
    import array
    a = array.array('h', samples)
    raw = a.tobytes()
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(raw)) + b'WAVE')
        f.write(b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b'data' + struct.pack('<I', len(raw)) + raw)


# ----------------------------------------------------------------------------- RWS
class Wave:
    def __init__(self, hdr, data):
        if len(hdr) < 0x70 + 16 + 32:
            raise ValueError('wave header too short (%d)' % len(hdr))
        self.const0 = hdr[0:4]
        self.fmtA = bytearray(hdr[4:48])
        self.fmtB = bytearray(hdr[48:92])
        self.positional = struct.unpack_from('<I', hdr, 92)[0]
        self.uuid = hdr[96:112]
        self.name_raw = hdr[112:-32]
        self.tail = hdr[-32:]
        self.data = data

    @property
    def name(self):
        return self.name_raw.split(b'\0')[0].decode('latin-1')

    @name.setter
    def name(self, s):
        b = s.encode('latin-1') + b'\0'
        b += bytes(-len(b) % 16)
        self.name_raw = b

    @property
    def rate(self):
        return struct.unpack_from('<I', self.fmtA, 0)[0]

    @rate.setter
    def rate(self, r):
        struct.pack_into('<I', self.fmtA, 0, r)
        struct.pack_into('<I', self.fmtB, 0, r)

    def set_data(self, data):
        self.data = data
        struct.pack_into('<I', self.fmtA, 8, len(data))
        struct.pack_into('<I', self.fmtB, 8, len(data))

    @property
    def codec_uuid(self):
        return bytes(self.fmtA[28:44])

    @property
    def nsamples(self):
        return len(self.data) // 16 * 28

    @property
    def seconds(self):
        return self.nsamples / self.rate if self.rate else 0

    def header_bytes(self):
        return (bytes(self.const0) + bytes(self.fmtA) + bytes(self.fmtB) +
                struct.pack('<I', self.positional) + bytes(self.uuid) + bytes(self.name_raw) + bytes(self.tail))

    def check(self):
        a = struct.unpack_from('<IIIBB', self.fmtA, 0)
        b = struct.unpack_from('<IIIBB', self.fmtB, 0)
        probs = []
        if a[2] != len(self.data) or b[2] != len(self.data):
            probs.append('fmt size %x/%x != data %x' % (a[2], b[2], len(self.data)))
        if a[0] != b[0]:
            probs.append('rate mismatch')
        if a[3] != 4 or a[4] != 1:
            probs.append('not 4-bit mono')
        if self.codec_uuid != VAG_UUID:
            probs.append('codec uuid %s' % self.codec_uuid.hex())
        if len(self.data) % 16:
            probs.append('data not multiple of 16')
        return probs


def _chunk(cid, payload):
    return struct.pack('<III', cid, len(payload), VER) + payload


class Bank:
    def __init__(self, raw=None):
        self.waves = []
        self.dict_hdr = b''
        self.versions_ok = True
        if raw is not None:
            self._parse(raw)

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read())

    def _hdr(self, d, o, want):
        cid, sz, ver = struct.unpack_from('<III', d, o)
        if cid != want:
            raise ValueError('expected chunk %x at %x, got %x' % (want, o, cid))
        if ver != VER:
            self.versions_ok = False
        return sz, o + 12

    def _parse(self, d):
        sz, o = self._hdr(d, 0, ID_DICT)
        if 12 + sz != len(d):
            raise ValueError('dict size %x != file size-12 %x' % (sz, len(d) - 12))
        hs, ho = self._hdr(d, o, ID_DHDR)
        self.dict_hdr = d[ho:ho + hs]
        o = ho + hs
        ls, lo = self._hdr(d, o, ID_LIST)
        n = struct.unpack_from('<I', d, lo)[0]
        p = lo + 4
        for _ in range(n):
            ws, wo = self._hdr(d, p, ID_WAVE)
            hs, ho = self._hdr(d, wo, ID_WHDR)
            ds, do = self._hdr(d, ho + hs, ID_WDATA)
            if (ho + hs - wo) + 12 + ds != ws:
                raise ValueError('wave chunk size mismatch at %x' % p)
            self.waves.append(Wave(d[ho:ho + hs], d[do:do + ds]))
            p = wo + ws
        if p != lo + ls:
            raise ValueError('wave list size mismatch')

    @property
    def dict_name(self):
        return self.dict_hdr[52:68].split(b'\0')[0].decode('latin-1')

    def to_bytes(self):
        lst = struct.pack('<I', len(self.waves))
        for w in self.waves:
            lst += _chunk(ID_WAVE, _chunk(ID_WHDR, w.header_bytes()) + _chunk(ID_WDATA, bytes(w.data)))
        return _chunk(ID_DICT, _chunk(ID_DHDR, bytes(self.dict_hdr)) + _chunk(ID_LIST, lst))

    def save(self, path):
        open(path, 'wb').write(self.to_bytes())

    def find(self, key):
        """index (int or decimal string) or wave name -> index"""
        if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
            i = int(key)
            if not 0 <= i < len(self.waves):
                raise IndexError('wave index %d out of range (0..%d)' % (i, len(self.waves) - 1))
            return i
        for i, w in enumerate(self.waves):
            if w.name.lower() == key.lower():
                return i
        raise KeyError('no wave named %r' % key)

    def new_wave(self, name, rate, adpcm, positional=0, template=0):
        t = self.waves[template]
        w = Wave(t.header_bytes(), b'')
        w.uuid = _uuid.uuid4().bytes
        w.name = name
        w.rate = rate
        w.positional = positional
        w.set_data(adpcm)
        return w

    def adpcm_total(self):
        return sum(len(w.data) for w in self.waves)


# ----------------------------------------------------------------------------- CRW
class Crw:
    def __init__(self, entries=None, header_count=None):
        self.entries = entries or []   # list of dict(category=int, name=str, attenuator=str)

    @classmethod
    def load(cls, path):
        txt = open(path, 'rb').read().decode('latin-1')
        lines = txt.replace('\r\n', '\n').split('\n')
        if lines[0].strip() != 'TXT1':
            raise ValueError('not a TXT1 .CRW')
        ents, cur = [], {}
        for ln in lines[2:]:
            s = ln.strip()
            if not s:
                continue
            if s == 'EndStruct':
                ents.append(cur)
                cur = {}
                continue
            k, _, v = s.partition(' ')
            cur[k] = v.strip()
        c = cls(ents)
        c.declared = int(lines[1].strip())
        c.blank_after_count = len(lines) > 2 and lines[2].strip() == ''
        return c

    def to_bytes(self):
        out = 'TXT1\r\n%d\r\n' % len(self.entries)
        if getattr(self, 'blank_after_count', False):
            out += '\r\n'
        for e in self.entries:
            out += 'category      %s\r\nname      %s\r\nattenuator      %s\r\nEndStruct\r\n\r\n' % (
                e['category'], e['name'], e['attenuator'])
        return out.encode('latin-1')

    def save(self, path):
        open(path, 'wb').write(self.to_bytes())


CATEGORIES = ['MUSIC', 'SFX', 'MENU', 'ENVIRONMENT', 'ENGINE', 'EFFECTS']


def crw_path_for(rws_path):
    base, _ = os.path.splitext(rws_path)
    for ext in ('.CRW', '.crw'):
        if os.path.exists(base + ext):
            return base + ext
    return None


def wav_to_adpcm(path, rate=None, gain_db=0.0, normalize=None, tail_frame=True):
    src, x = read_wav(path)
    rate = rate or src
    x = resample(x, src, rate)
    if gain_db:
        x = x * (10 ** (gain_db / 20.0))
    s = to_int16(x, normalize)
    return rate, adpcm_encode(s, pad_silent_frame=tail_frame), len(s)
