"""Ekspor tabel ke Excel (.xlsx) yang rapi: judul tebal berwarna, lebar kolom otomatis, filter, panel beku."""
import io

import pandas as pd
import streamlit as st
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FMT_MASSAL = {"Peluang P1": "0.0%", "Peluang P2": "0.0%", "Peluang Min. 1 Lolos": "0.0%",
              "Nilai Komposit": "0.00", "Nilai Pendukung P1": "0.00", "Nilai Pendukung P2": "0.00"}
KOLOM_PRODI = ["ptn", "prodi", "jenjang", "dt_2025", "peminat_2025", "dt_2026", "keketatan_prodi",
               "alumni_jur", "jenis_mapel", "provinsi", "kota"]
NAMA_PRODI = {"ptn": "PTN", "prodi": "Program Studi", "jenjang": "Jenjang", "dt_2025": "DT 2025",
              "peminat_2025": "Peminat 2025", "dt_2026": "DT 2026", "keketatan_prodi": "Keketatan",
              "alumni_jur": "Alumni Jurusan", "jenis_mapel": "Mapel Pendukung", "provinsi": "Provinsi", "kota": "Kab/Kota"}


def tabel_prodi(d):
    return d[KOLOM_PRODI].rename(columns=NAMA_PRODI)


def _tulis_lembar(w, df, sheet, fmt, link_cols):
    sheet = "".join(c for c in sheet if c not in "[]:*?/\\")[:31] or "Data"
    df.to_excel(w, index=False, sheet_name=sheet)
    ws = w.sheets[sheet]
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"
    if len(df):
        ws.auto_filter.ref = ws.dimensions
    for i, col in enumerate(df.columns, 1):
        huruf = get_column_letter(i)
        isi = df[col].head(2000).astype(str).str.len().max() if len(df) else 0
        isi = 0 if pd.isna(isi) else isi
        lebar = min(max(isi + 2, len(str(col)) + 4, 8), 60)
        if col in link_cols:
            lebar = min(lebar, 30)
        ws.column_dimensions[huruf].width = float(lebar)
        for sel in ws[huruf][1:]:
            if col in fmt:
                sel.number_format = fmt[col]
            if col in link_cols and isinstance(sel.value, str) and sel.value.startswith("http"):
                sel.hyperlink = sel.value
                sel.font = Font(color="0563C1", underline="single")


def to_xlsx_multi(lembar):
    """lembar = [(nama_lembar, df, fmt, kolom_tautan), ...]"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nama, df, fmt, link_cols in lembar:
            _tulis_lembar(w, df, nama, fmt or {}, tuple(link_cols or ()))
    return buf.getvalue()


def to_xlsx(df, sheet="Data", fmt=None):
    return to_xlsx_multi([(sheet, df, fmt, ())])


@st.cache_data(show_spinner=False, max_entries=20)
def _xlsx_cache(df, sheet, fmt):
    return to_xlsx(df, sheet, fmt)


@st.cache_data(show_spinner=False, max_entries=10)
def _xlsx_multi_cache(lembar):
    return to_xlsx_multi(lembar)


def tombol_xlsx(label, df, nama_file, sheet="Data", fmt=None, key=None):
    st.download_button(label, _xlsx_cache(df, sheet, fmt or {}), file_name=nama_file, mime=XLSX_MIME, key=key)


def tombol_xlsx_multi(label, lembar, nama_file, key=None):
    st.download_button(label, _xlsx_multi_cache(lembar), file_name=nama_file, mime=XLSX_MIME, key=key)
