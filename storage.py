"""Penyimpanan pilihan siswa.

* Jika Secrets Streamlit berisi `sheet_id` + `gcp_json`  -> disimpan PERMANEN di Google Sheets.
* Jika tidak                                              -> disimpan di data/pilihan_siswa.csv (lokal).
Yang disimpan hanya nomor urut siswa + pilihan PTN/prodi + nilai (tanpa nama/NISN).
"""
import json
import traceback
from datetime import datetime, timedelta, timezone
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
    lama = dict(data)                         # rekaman diganti (bukan diubah di tempat), jadi salinan dangkal cukup
    for no, rec in perubahan.items():
        if rec is None:
            data.pop(int(no), None)
        else:
            data[int(no)] = {k: rec.get(k) for k in HEADER[1:]}
    _tulis(data)
    baca.clear()
    try:                                      # riwayat bersifat tambahan: gagal mencatat TIDAK boleh membatalkan simpan
        catat_riwayat(lama, data, [int(n) for n in perubahan])
    except Exception:  # noqa: BLE001
        pass
    return data


# =====================================================================
#  Daftar rekomendasi yang disimpan untuk siswa (ditampilkan di Portal Siswa)
#  Disimpan sebagai "resep" (mapel + filter), bukan salinan tabel -> ringan & selalu mengikuti data terbaru.
# =====================================================================
REK_SHEET = "Rekomendasi"
REK_COLS = ["id", "no", "tanggal", "judul", "catatan", "sumber", "mapel", "nilai", "status_filter",
            "jenjang", "provinsi", "ptn", "cari", "sembunyi", "batas"]
REK_CSV = m.DATA / "rekomendasi_siswa.csv"


@st.cache_resource(show_spinner=False)
def _worksheet_rek(sid, info_str):
    import gspread
    gc = gspread.service_account_from_dict(json.loads(info_str), scopes=SCOPES)
    sh = gc.open_by_key(sid)
    try:
        ws = sh.worksheet(REK_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=REK_SHEET, rows=1000, cols=len(REK_COLS))
    if ws.row_values(1) != REK_COLS:
        ws.update(range_name="A1", values=[REK_COLS])
    return ws


def _f(v, default=0.0):
    try:
        x = float(v)
        return default if np.isnan(x) else x
    except (TypeError, ValueError):
        return default


def _s(v):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()


def _rapikan_rek(rows):
    out = []
    for r in rows:
        try:
            rid, no = int(r["id"]), int(r["no"])
        except (TypeError, ValueError, KeyError):
            continue
        out.append({
            "id": rid, "no": no, "tanggal": _s(r.get("tanggal")), "judul": _s(r.get("judul")),
            "catatan": _s(r.get("catatan")), "sumber": _s(r.get("sumber")) or "Pilihan 1",
            "mapel": _s(r.get("mapel")), "nilai": _f(r.get("nilai")),
            "status_filter": _s(r.get("status_filter")) or "Semua", "jenjang": _s(r.get("jenjang")),
            "provinsi": _s(r.get("provinsi")), "ptn": _s(r.get("ptn")), "cari": _s(r.get("cari")),
            "sembunyi": int(_f(r.get("sembunyi"), 1)), "batas": int(_f(r.get("batas"), 100)) or 100})
    return sorted(out, key=lambda x: x["id"])


def _baca_rek_mentah():
    cfg = _secrets()
    if cfg:
        try:
            ws = _worksheet_rek(*cfg)
            rows = ws.get_all_records(value_render_option="UNFORMATTED_VALUE")
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return _rapikan_rek(rows)
    if REK_CSV.exists():
        try:
            return _rapikan_rek(pd.read_csv(REK_CSV, keep_default_na=False).to_dict("records"))
        except Exception:
            return []
    return []


def _tulis_rek(rows):
    from openpyxl.utils import get_column_letter
    baris = [[_py(r.get(k)) for k in REK_COLS] for r in rows]
    cfg = _secrets()
    if cfg:
        try:
            ws = _worksheet_rek(*cfg)
            values = [REK_COLS] + baris
            lama = len(ws.col_values(1))
            if ws.row_count < len(values):
                ws.add_rows(len(values) - ws.row_count + 50)
            if ws.col_count < len(REK_COLS):
                ws.add_cols(len(REK_COLS) - ws.col_count)
            ws.update(range_name="A1", values=values)
            if lama > len(values):
                ws.batch_clear([f"A{len(values) + 1}:{get_column_letter(len(REK_COLS))}{lama}"])
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return
    try:
        pd.DataFrame(baris, columns=REK_COLS).to_csv(REK_CSV, index=False)
    except OSError:
        raise PenyimpananError("Tidak bisa menulis file di server ini (read-only). Aktifkan penyimpanan Google Sheets.")


@st.cache_data(ttl=15, show_spinner=False)
def baca_rek():
    """Semua daftar rekomendasi (cache 15 detik)."""
    return _baca_rek_mentah()


def tambah_rek(rec):
    """Tambah satu daftar. `id` dibuat otomatis. Mengembalikan seluruh daftar terbaru."""
    rows = _baca_rek_mentah()
    rec = dict(rec, id=max([r["id"] for r in rows], default=0) + 1)
    rows.append(_rapikan_rek([rec])[0])
    _tulis_rek(rows)
    baca_rek.clear()
    return rows


def hapus_rek(rid):
    rows = [r for r in _baca_rek_mentah() if r["id"] != int(rid)]
    _tulis_rek(rows)
    baca_rek.clear()
    return rows


# =====================================================================
#  Keterangan manual per siswa (kolom "Keterangan" di Pemetaan Massal)
# =====================================================================
KET_SHEET = "Keterangan"
KET_COLS = ["no", "catatan"]
KET_CSV = m.DATA / "keterangan_siswa.csv"


@st.cache_resource(show_spinner=False)
def _worksheet_ket(sid, info_str):
    import gspread
    gc = gspread.service_account_from_dict(json.loads(info_str), scopes=SCOPES)
    sh = gc.open_by_key(sid)
    try:
        ws = sh.worksheet(KET_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=KET_SHEET, rows=500, cols=len(KET_COLS))
    if ws.row_values(1) != KET_COLS:
        ws.update(range_name="A1", values=[KET_COLS])
    return ws


def _rapikan_ket(rows):
    out = {}
    for r in rows:
        try:
            no = int(r["no"])
        except (TypeError, ValueError, KeyError):
            continue
        t = _s(r.get("catatan"))
        if t:
            out[no] = t
    return out


def _baca_ket_mentah():
    cfg = _secrets()
    if cfg:
        try:
            rows = _worksheet_ket(*cfg).get_all_records(value_render_option="UNFORMATTED_VALUE")
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return _rapikan_ket(rows)
    if KET_CSV.exists():
        try:
            return _rapikan_ket(pd.read_csv(KET_CSV, keep_default_na=False).to_dict("records"))
        except Exception:
            return {}
    return {}


def _tulis_ket(data):
    baris = [[int(no), str(t)] for no, t in sorted(data.items())]
    cfg = _secrets()
    if cfg:
        try:
            ws = _worksheet_ket(*cfg)
            values = [KET_COLS] + baris
            lama = len(ws.col_values(1))
            if ws.row_count < len(values):
                ws.add_rows(len(values) - ws.row_count + 50)
            if ws.col_count < len(KET_COLS):
                ws.add_cols(len(KET_COLS) - ws.col_count)
            ws.update(range_name="A1", values=values)
            if lama > len(values):
                ws.batch_clear([f"A{len(values) + 1}:B{lama}"])
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return
    try:
        pd.DataFrame(baris, columns=KET_COLS).to_csv(KET_CSV, index=False)
    except OSError:
        raise PenyimpananError("Tidak bisa menulis file di server ini (read-only). Aktifkan penyimpanan Google Sheets.")


@st.cache_data(ttl=15, show_spinner=False)
def baca_ket():
    """{no_siswa: catatan manual} (cache 15 detik)."""
    return _baca_ket_mentah()


def perbarui_ket(perubahan):
    """perubahan = {no: teks | None/'' (= hapus catatan, kembali ke teks otomatis)}. Membaca data terbaru dulu lalu menggabungkan."""
    data = _baca_ket_mentah()
    for no, t in perubahan.items():
        t = _s(t)
        if t:
            data[int(no)] = t
        else:
            data.pop(int(no), None)
    _tulis_ket(data)
    baca_ket.clear()
    return data


# =====================================================================
#  Riwayat perubahan pilihan siswa ("A memilih prodi X di kampus B") - ditampilkan di dashboard Tampilan
#  Dicatat otomatis oleh perbarui() dengan membandingkan data lama vs baru. Hanya ditambah, tidak pernah ditimpa.
# =====================================================================
RIW_SHEET = "Riwayat"
RIW_COLS = ["waktu", "no", "aksi", "pilihan", "ptn_baru", "prodi_baru", "nilai_baru", "ptn_lama", "prodi_lama"]
RIW_CSV = m.DATA / "riwayat_pilihan.csv"
RIW_MAKS = 1000                               # jumlah catatan terbaru yang dibaca
WIB = timezone(timedelta(hours=7))


def hitung_peristiwa(lama, baru, daftar_no, waktu):
    """Bandingkan pilihan lama vs baru untuk siswa di `daftar_no`. Hanya perubahan PTN/prodi yang dicatat
    (mengubah nilai pendukung saja tidak dihitung). aksi: memilih | mengganti | menghapus."""
    out = []
    for no in daftar_no:
        a, b = lama.get(no) or {}, baru.get(no) or {}
        for k in ("1", "2"):
            pl = (_s(a.get(f"ptn{k}")), _s(a.get(f"prodi{k}")))
            pb = (_s(b.get(f"ptn{k}")), _s(b.get(f"prodi{k}")))
            ada_l, ada_b = bool(pl[0] and pl[1]), bool(pb[0] and pb[1])
            if (not ada_l and not ada_b) or (ada_l and ada_b and pl == pb):
                continue
            out.append({"waktu": waktu, "no": int(no), "pilihan": int(k),
                        "aksi": "memilih" if not ada_l else ("menghapus" if not ada_b else "mengganti"),
                        "ptn_baru": pb[0] if ada_b else "", "prodi_baru": pb[1] if ada_b else "",
                        "nilai_baru": _f(b.get(f"nilai{k}"), "") if ada_b else "",
                        "ptn_lama": pl[0] if ada_l else "", "prodi_lama": pl[1] if ada_l else ""})
    return out


@st.cache_resource(show_spinner=False)
def _worksheet_riw(sid, info_str):
    import gspread
    gc = gspread.service_account_from_dict(json.loads(info_str), scopes=SCOPES)
    sh = gc.open_by_key(sid)
    try:
        ws = sh.worksheet(RIW_SHEET)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=RIW_SHEET, rows=2000, cols=len(RIW_COLS))
    if ws.row_values(1) != RIW_COLS:
        ws.update(range_name="A1", values=[RIW_COLS])
    return ws


def catat_riwayat(lama, baru, daftar_no):
    """Tambahkan catatan perubahan ke Riwayat (Google Sheets atau CSV lokal). Mengembalikan jumlah catatan."""
    waktu = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
    ev = hitung_peristiwa(lama, baru, daftar_no, waktu)
    if not ev:
        return 0
    baris = [[_py(e.get(k)) for k in RIW_COLS] for e in ev]
    cfg = _secrets()
    if cfg:
        try:
            _worksheet_riw(*cfg).append_rows(baris, value_input_option="RAW")
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
    else:
        try:
            ada = pd.read_csv(RIW_CSV, keep_default_na=False) if RIW_CSV.exists() else pd.DataFrame(columns=RIW_COLS)
            pd.concat([ada, pd.DataFrame(baris, columns=RIW_COLS)], ignore_index=True).to_csv(RIW_CSV, index=False)
        except OSError:
            raise PenyimpananError("Tidak bisa menulis riwayat (server read-only).")
    baca_riwayat.clear()
    return len(ev)


def _rapikan_riw(rows):
    out = []
    for r in rows:
        try:
            no, pil = int(r["no"]), int(r["pilihan"])
        except (TypeError, ValueError, KeyError):
            continue
        w = _s(r.get("waktu"))
        aksi = _s(r.get("aksi"))
        if not w or aksi not in ("memilih", "mengganti", "menghapus"):
            continue
        nb = r.get("nilai_baru")
        out.append({"waktu": w, "no": no, "aksi": aksi, "pilihan": pil, "ptn_baru": _s(r.get("ptn_baru")),
                    "prodi_baru": _s(r.get("prodi_baru")),
                    "nilai_baru": None if _s(nb) == "" else _f(nb, None),
                    "ptn_lama": _s(r.get("ptn_lama")), "prodi_lama": _s(r.get("prodi_lama"))})
    out.reverse()                                          # baris terakhir ditulis = paling baru
    out.sort(key=lambda x: x["waktu"], reverse=True)       # urut stabil: terbaru di atas
    return out[:RIW_MAKS]


@st.cache_data(ttl=15, show_spinner=False)
def baca_riwayat():
    """Catatan perubahan pilihan, terbaru di atas (cache 15 detik)."""
    cfg = _secrets()
    if cfg:
        try:
            rows = _worksheet_riw(*cfg).get_all_records(value_render_option="UNFORMATTED_VALUE")
        except PenyimpananError:
            raise
        except Exception as e:  # noqa: BLE001
            raise _terjemah(e)
        return _rapikan_riw(rows)
    if RIW_CSV.exists():
        try:
            return _rapikan_riw(pd.read_csv(RIW_CSV, keep_default_na=False).to_dict("records"))
        except Exception:  # noqa: BLE001
            return []
    return []
