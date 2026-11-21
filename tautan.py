"""Kode & tautan pribadi siswa untuk Portal Siswa.
Kode dibuat dari nomor siswa + 'garam' rahasia (HMAC), jadi tidak perlu disimpan dan tidak bisa ditebak.
Garam diambil dari Secrets `portal_salt` (opsional); jika tidak ada, diturunkan dari kunci Google (gcp_json)."""
import base64
import hashlib
import hmac
import json

import streamlit as st


def _garam():
    try:
        g = st.secrets.get("portal_salt")
        if g:
            return str(g).encode()
        raw = st.secrets.get("gcp_json")
        if raw:
            return hashlib.sha256(str(json.loads(raw).get("private_key", raw)).encode()).digest()
    except Exception:  # noqa: BLE001
        pass
    return b"snbp-lokal"


def kode_siswa(no):
    d = hmac.new(_garam(), f"siswa:{int(no)}".encode(), hashlib.sha256).digest()
    return base64.b32encode(d).decode().lower()[:10]


def cari_siswa(kode, siswa_df):
    """Mengembalikan nomor siswa untuk kode ini, atau None bila tidak valid."""
    kode = str(kode or "").strip().lower()
    if not kode:
        return None
    ketemu = None
    for no in siswa_df["no"]:
        if hmac.compare_digest(kode_siswa(no), kode):
            ketemu = int(no)
    return ketemu


def portal_url():
    try:
        return str(st.secrets.get("portal_url") or "").strip().rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def tautan(no):
    base = portal_url()
    return f"{base}/?k={kode_siswa(no)}" if base else f"?k={kode_siswa(no)}"
