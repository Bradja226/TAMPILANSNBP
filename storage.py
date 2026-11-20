"""Penyimpanan pilihan siswa.

* Jika Secrets Streamlit berisi `sheet_id` + `gcp_json`  -> disimpan PERMANEN di Google Sheets.
* Jika tidak                                              -> disimpan di data/pilihan_siswa.csv (lokal).
Yang disimpan hanya nomor urut siswa + pilihan PTN/prodi + nilai (tanpa nama/NISN).
"""
import json
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import model as m

CSV = m.DATA / "pilihan_siswa.csv"
HEADER = m.PIL_COLS                       # no, ptn1, prodi1, nilai1, ptn2, prodi2, nilai2
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class PenyimpananError(Exception):
    """Pesan error yang aman & mudah dipahami untuk ditampilkan ke pengguna."""


# ---------------------------------------------------------------- konfigurasi
def _secrets():
    """Mengembalikan (sheet_id, info_json_str) atau None bila mode Google Sheets tidak dipakai."""
    try:
        sid = st.secrets.get("sheet_id")
        raw = st.secrets.get("gcp_json")
        tbl = st.secrets.get("gcp_service_account")
    except Exception:
        return None
    if not sid:
        return None
    if raw:
        try:
            info = json.loads(raw)
        except Exception:
            raise PenyimpananError("Isi `gcp_json` di Secrets bukan JSON yang valid. Tempel ULANG seluruh isi file .json "
                                   "(dari tanda { sampai }) di antara tanda ''' dan '''.")
    elif tbl:
        info = dict(tbl)
    else:
        raise PenyimpananError("`sheet_id` sudah ada di Secrets, tetapi `gcp_json` belum diisi.")
    return str(sid).strip(), json.dumps(info, sort_keys=True)


def nama_mode():
    try:
        return "Google Sheets (permanen)" if _secrets() else "File lokal (CSV)"
    except PenyimpananError:
        return "Google Sheets (konfigurasi bermasalah)"


def _terjemah(e):
    s, n = str(e), type(e).__name__
    low = s.lower()
    if n == "SpreadsheetNotFound" or "not found" in low or "404" in s:
        hint = ("Google Sheet tidak ditemukan. Periksa `sheet_id` dan pastikan Sheet sudah di-Share ke email robot "
                "(service account) dengan peran Editor.")
    elif "has not been used" in low or "is disabled" in low or "sheets api" in low or "drive api" in low:
        hint = "Google Sheets API belum diaktifkan di Google Cloud (menu APIs & Services → Library → Enable)."
    elif "403" in s or "permission" in low:
        hint = "Akses ditolak. Pastikan Sheet di-Share ke email robot sebagai Editor."
    else:
        hint = "Gagal terhubung ke Google Sheets."
    try:
        lokasi = " > ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}"
                            for f in traceback.extract_tb(e.__traceback__)[-4:])
    except Exception:  # noqa: BLE001
        lokasi = "-"
    return PenyimpananError(f"{hint} (detail: {type(e).__module__}.{n} {e.args!r} | lokasi: {lokasi})")


# ---------------------------------------------------------------- Google Sheets
@st.cache_resource(show_spinner=False)
def _worksheet(sid, info_str):
    import gspread
    gc = gspread.service_account_from_dict(json.loads(info_str), scopes=SCOPES)
    ws = gc.open_by_key(sid).sheet1
    if ws.row_values(1) != HEADER:        # sheet baru/kosong -> pasang judul kolom
        ws.update(range_name="A1", values=[HEADER])
    return ws


def _rapikan(rows):
    """list[dict] mentah -> {no: {ptn1, prodi1, nilai1, ptn2, prodi2, nilai2}}"""
    out = {}
    for r in rows:
        try:
            no = int(r["no"])
        except (TypeError, ValueError, KeyError):
            continue
        rec = {}
        for k in HEADER[1:]:
            v = r.get(k)
            if v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
                rec[k] = None
            elif k.startswith("nilai"):
                try:
                    rec[k] = float(v)
                except (TypeError, ValueError):
                    rec[k] = None
            else:
                rec[k] = str(v).strip()
        out[no] = rec
    return out


def _baca_mentah():
    cfg = _secrets()
    if cfg:
        try:
            ws = _worksheet(*cfg)
            rows = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return _rapikan(rows)
    if CSV.exists():
        try:
            return _rapikan(pd.read_csv(CSV).to_dict("records"))
        except Exception:
            return {}
    return {}


def _py(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def _tulis(data):
    baris = [[int(no)] + [_py(rec.get(k)) for k in HEADER[1:]] for no, rec in sorted(data.items())]
    cfg = _secrets()
    if cfg:
        try:
            ws = _worksheet(*cfg)
            values = [HEADER] + baris
            lama = len(ws.col_values(1))
            if ws.row_count < len(values):
                ws.add_rows(len(values) - ws.row_count + 50)
            if ws.col_count < len(HEADER):
                ws.add_cols(len(HEADER) - ws.col_count)
            ws.update(range_name="A1", values=values)
            if lama > len(values):             # bersihkan sisa baris lama (mis. setelah hapus)
                ws.batch_clear([f"A{len(values) + 1}:G{lama}"])
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return
    try:
        pd.DataFrame(baris, columns=HEADER).to_csv(CSV, index=False)
    except OSError:
        raise PenyimpananError("Tidak bisa menulis file di server ini (read-only). Aktifkan penyimpanan Google Sheets.")


# ---------------------------------------------------------------- API untuk aplikasi
@st.cache_data(ttl=15, show_spinner=False)
def baca():
    """Seluruh pilihan siswa. Di-cache 15 detik agar tidak membebani Google (kuota)."""
    return _baca_mentah()


def perbarui(perubahan):
    """perubahan = {no: {rec} | None(=hapus)}. Selalu membaca data TERBARU dulu lalu menggabungkan,
    sehingga edit orang lain tidak tertimpa. Mengembalikan seluruh data terbaru."""
    data = _baca_mentah()
    for no, rec in perubahan.items():
        if rec is None:
            data.pop(int(no), None)
        else:
            data[int(no)] = {k: rec.get(k) for k in HEADER[1:]}
    _tulis(data)
    baca.clear()
    return data
