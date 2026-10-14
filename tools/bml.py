#!/usr/bin/env python3
"""Read and edit MotoGP 08 .BML files (binary XML: UTF-32 names and text values).

Usage:
  bml.py dump FILE.BML                       print the tree as indented text
  bml.py set FILE.BML OUT.BML PATH=VALUE...  change text values (PATH like General/OutOfTrack_Self)
"""
import argparse
import struct
import sys


def _str(d, o, nbytes):
    return d[o:o + nbytes].decode("utf-32-le").rstrip("\0")


class Node:
    """header (9 u32): 0x24, node size, kind (1 element, 3 text), text offset, attribute count,
    attribute offset, child count, child offset, name byte length; then the UTF-32 name"""

    def __init__(self, d, o):
        self.off = o
        w = struct.unpack_from("<9I", d, o)
        if w[0] != 0x24:
            raise ValueError("not a BML node at 0x%x" % o)
        self.size, self.kind = w[1], w[2]
        self.name = _str(d, o + 0x24, w[8])
        self.value = None; self.value_off = None; self.children = []; self.attrs = []
        if self.kind == 3:                      # text: UTF-32 value, its byte length just before it
            p = o + w[3]
            self.value_off, self.value_len = p, struct.unpack_from("<I", d, p - 4)[0]
            self.value = _str(d, p, self.value_len)
        p = o + w[5] - 4
        for _ in range(w[4]):                   # attribute: record size, ?, name length, name, value length, value
                                                # (the attribute offset points just after the record size)
            rsz, _unk, nl = struct.unpack_from("<3I", d, p)
            assert _unk == 0
            vl = struct.unpack_from("<I", d, p + 12 + nl)[0]
            self.attrs.append([_str(d, p + 12, nl), _str(d, p + 16 + nl, vl), p + 16 + nl, vl])
            self.attr_unk = _unk
            p += rsz
        p = o + w[7]
        for _ in range(w[6]):
            c = Node(d, p)
            self.children.append(c)
            p += c.size

    def text(self):
        return next((c.value for c in self.children if c.kind == 3), None)

    def walk(self, path=""):
        here = (path + "/" + self.name) if self.kind != 3 else path
        yield here, self
        for c in self.children:
            yield from c.walk(here)


def _u32(*v):
    return struct.pack("<%dI" % len(v), *v)


def _utf32(t):
    return (t + "\0").encode("utf-32-le")


def element(name, attrs=(), text=None, children=()):
    """a new element node (attrs: [(name, value)]); `text` adds a text child"""
    n = Node.__new__(Node)
    n.kind, n.name, n.value, n.children = 1, name, None, list(children)
    n.attrs = [[k, v, None, None] for k, v in attrs]
    if text is not None:
        t = Node.__new__(Node)
        t.kind, t.name, t.value, t.children, t.attrs = 3, "text", text, [], []
        n.children.insert(0, t)
    return n


def build(n):
    """serialise a node (and its children) back to bytes"""
    name = _utf32(n.name)
    if n.kind == 3:
        val = _utf32(n.value)
        body = name + _u32(len(val)) + val + _u32(0)
        return _u32(0x24, 0x24 + len(body), 3, 0x24 + len(name) + 4, 0, 0, 0, 0, len(name)) + body
    attrs = b""
    for k, v, *_ in n.attrs:
        kb, vb = _utf32(k), _utf32(v)
        attrs += _u32(16 + len(kb) + len(vb), 0, len(kb)) + kb + _u32(len(vb)) + vb
    kids = b"".join(build(c) for c in n.children)
    head = len(name) + len(attrs) + 4
    size = 0x24 + head + len(kids)
    return _u32(0x24, size, n.kind, 0, len(n.attrs), 0x24 + len(name) + 4 if n.attrs else 0,
                len(n.children), 0x24 + head if n.children else 0, len(name)) + name + attrs + _u32(0) + kids


def count(n):
    return 1 + sum(count(c) for c in n.children)


def save(root):
    """whole file: header, then the root (the game files leave out the final zero word)"""
    b = build(root)
    assert b[-4:] == bytes(4)
    return _u32(0, 12, count(root), 0) + b[:-4]


def load(d):
    return Node(d, struct.unpack_from("<I", d, 4)[0] + 4)


def dump(d, out=sys.stdout):
    def rec(n, depth):
        attrs = "".join(' %s="%s"' % (k, v) for k, v, _, _ in n.attrs)
        txt = n.text()
        out.write("  " * depth + n.name + attrs + (" = %r" % txt if txt is not None else "") + "\n")
        for c in n.children:
            if c.kind != 3:
                rec(c, depth + 1)
    rec(load(d), 0)


def set_values(d, changes):
    """changes {path: value}; a value must not need more room than the old one"""
    d = bytearray(d)
    found = set()
    for path, n in load(d).walk():
        if n.kind == 3 and path.lstrip("/") in changes or n.kind == 3 and path.split("/", 2)[-1] in changes:
            key = path.lstrip("/") if path.lstrip("/") in changes else path.split("/", 2)[-1]
            new = changes[key].encode("utf-32-le") + b"\0\0\0\0"
            if len(new) > n.value_len:
                raise ValueError("%s: %r is longer than %r" % (key, changes[key], n.value))
            d[n.value_off:n.value_off + n.value_len] = new + bytes(n.value_len - len(new))
            found.add(key)
    missing = set(changes) - found
    if missing:
        raise KeyError("not found: " + ", ".join(sorted(missing)))
    return bytes(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump"); p.add_argument("bml")
    p = sub.add_parser("set"); p.add_argument("bml"); p.add_argument("out"); p.add_argument("changes", nargs="+")
    a = ap.parse_args()
    d = open(a.bml, "rb").read()
    if a.cmd == "dump":
        dump(d)
    else:
        ch = dict(c.split("=", 1) for c in a.changes)
        open(a.out, "wb").write(set_values(d, ch))


if __name__ == "__main__":
    main()
