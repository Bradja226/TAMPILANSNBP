"""Dashboard TAMPILAN SAJA (read-only): Pemetaan Massal + Data Prodi + Data PTN.
Membaca penyimpanan yang sama dengan app.py (Google Sheets / CSV), otomatis ter-refresh tiap 30 detik.
Tidak ada tombol simpan / hapus / impor di sini."""
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import model as m
import batas_ui
import storage
from exportxl import FMT_MASSAL, tombol_xlsx

ALLOW_DOWNLOAD = False   # ubah ke True jika pengguna tampilan boleh mengunduh data
REFRESH_DETIK = 30

st.set_page_config(page_title="Pemetaan SNBP 2027 (Tampilan)", page_icon="👁️", layout="wide")
IKON = {"AMAN": "🟢", "KOMPETITIF": "🟡", "BERISIKO": "🔴", "": ""}
st.markdown("<style>.block-container{padding-top:2rem;}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Memuat database…")
def muat_ref():
    return m.Ref()


R = muat_ref()
CUT_A, CUT_K = R.params["cut_aman"], R.params["cut_kompetitif"]


def baca_pilihan():
    """Baca data terbaru (cache 15 dtk) dari penyimpanan yang sama dengan dashboard Edit."""
    try:
        return storage.baca()
    except Exception as e:  # noqa: BLE001
        st.error(f"⚠️ Gagal membaca penyimpanan: {e}")
        return {}


def tombol_unduh(df, nama, sheet="Data", fmt=None):
    if ALLOW_DOWNLOAD:
        tombol_xlsx("⬇️ Unduh Excel", df, nama, sheet, fmt, key="x_" + nama)


st.title("👁️ Pemetaan SNBP 2027")
st.caption("Tampilan saja — data tidak dapat diubah dari halaman ini.")
tab_mas, tab_prodi, tab_ptn = st.tabs(["👥 Pemetaan Massal", "📚 Data Prodi", "🏛️ Data PTN"])


@st.fragment(run_every=REFRESH_DETIK)
def tampil_massal():
    tb = m.tabel_massal(R, baca_pilihan(), CUT_A, CUT_K)
    try:
        ket = storage.baca_ket()
    except Exception as e:  # noqa: BLE001
        ket = {}
        st.error(f"⚠️ Gagal membaca keterangan: {e}")
    tb, per_ptn, elim, _ = m.tambahkan_info_batas(R, tb, ket)
    ok = tb[tb["Peluang P1"].notna()]
    if st.button("🔄 Muat ulang sekarang"):
        st.rerun()
    sumber = storage.nama_mode()
    if "File lokal" in sumber:
        st.warning("⚠️ Dashboard ini BELUM terhubung ke Google Sheets, jadi tabel kosong. Buka ⋮ → Settings → Secrets "
                   "pada aplikasi ini, tempel `sheet_id` dan `gcp_json` yang sama dengan aplikasi Edit, lalu Save.")
    st.caption(f"Sumber data: {sumber} · {len(tb[tb['Peluang P1'].notna()])} siswa terpetakan · "
               f"diperbarui otomatis tiap {REFRESH_DETIK} detik · terakhir dibaca {pd.Timestamp.now():%H:%M:%S}")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total siswa", len(tb))
    k2.metric("Sudah dipetakan", len(ok), f"{len(ok) / len(tb) * 100:.0f}%", delta_color="off")
    k3.metric("🟢 Pilihan 1 AMAN", int((tb["Status P1"] == "AMAN").sum()))
    k4.metric("🔴 Perlu evaluasi ulang", int((tb["Saran Strategi"] == "Evaluasi Ulang Kedua Pilihan").sum()))

    if len(ok):
        g1, g2 = st.columns(2)
        sc = ok["Saran Strategi"].value_counts().reset_index()
        sc.columns = ["Strategi", "Jumlah"]
        g1.plotly_chart(px.bar(sc, x="Jumlah", y="Strategi", orientation="h", title="Saran strategi kombinasi",
                               color="Strategi", color_discrete_map={
                                   "Kombinasi Ideal (Ada Opsi Aman)": "#16a34a", "Perlu Pengaman di Pilihan 2": "#f59e0b",
                                   "Evaluasi Ulang Kedua Pilihan": "#dc2626", "Isi Pilihan 2 sebagai pengaman": "#64748b"})
                        .update_layout(showlegend=False, height=300, yaxis_title=None), key="v_strat")
        top = ok["PTN Pilihan 1"].value_counts().head(10).reset_index()
        top.columns = ["PTN", "Jumlah siswa"]
        g2.plotly_chart(px.bar(top, x="Jumlah siswa", y="PTN", orientation="h", title="10 PTN terbanyak dipilih (Pilihan 1)")
                        .update_layout(height=300, yaxis={"autorange": "reversed"}, yaxis_title=None), key="v_top")

    batas_ui.render_pemantau(R, per_ptn, elim, "v")

    f1, f2, f3, f4 = st.columns(4)
    kelas_f = f1.multiselect("Kelas", sorted(tb["Kelas"].unique()), key="v_kelas")
    strat_f = f2.multiselect("Saran strategi", sorted(x for x in tb["Saran Strategi"].unique() if x), key="v_strat_f")
    ptn_f = f3.multiselect("PTN Pilihan 1", sorted(ok["PTN Pilihan 1"].dropna().unique()), key="v_ptn")
    cari = f4.text_input("Cari nama siswa", key="v_cari")
    hanya = st.checkbox("Hanya yang sudah dipetakan", key="v_hanya")
    sb = st.selectbox("Status batas PTN", ["Semua", "⚠️ Lewat batas", "✅ Dalam batas"], key="v_sb")
    v = tb.copy()
    if kelas_f:
        v = v[v["Kelas"].isin(kelas_f)]
    if strat_f:
        v = v[v["Saran Strategi"].isin(strat_f)]
    if ptn_f:
        v = v[v["PTN Pilihan 1"].isin(ptn_f)]
    if cari:
        v = v[v["Nama Siswa"].str.contains(cari, case=False, na=False)]
    if hanya:
        v = v[v["Peluang P1"].notna()]
    if sb != "Semua":
        v = v[v["Status Batas"] == sb]

    t = v.copy()
    for c in ("Peluang P1", "Peluang P2", "Peluang Min. 1 Lolos"):
        t[c] = t[c] * 100
    for c in ("Status P1", "Status P2"):
        t[c] = t[c].map(lambda s: f"{IKON[s]} {s}" if s else "")
    st.dataframe(t, hide_index=True, height=520, column_config={
        "Keterangan": st.column_config.TextColumn(width="large"),
        "PTN Pilihan 1": st.column_config.TextColumn(width="large"), "Prodi Pilihan 1": st.column_config.TextColumn(width="large"), "PTN Pilihan 2": st.column_config.TextColumn(width="large"), "Prodi Pilihan 2": st.column_config.TextColumn(width="large"), "Nama Siswa": st.column_config.TextColumn(width="medium"), "Saran Strategi": st.column_config.TextColumn(width="large"),
        "Nilai Komposit": st.column_config.NumberColumn(format="%.2f"),
        "Nilai Pendukung P1": st.column_config.NumberColumn(format="%.2f"),
        "Nilai Pendukung P2": st.column_config.NumberColumn(format="%.2f"),
        "Peluang P1": st.column_config.NumberColumn("Peluang P1 (%)", format="%.1f"),
        "Peluang P2": st.column_config.NumberColumn("Peluang P2 (%)", format="%.1f"),
        "Peluang Min. 1 Lolos": st.column_config.NumberColumn("Peluang min. 1 lolos (%)", format="%.1f")})
    tombol_unduh(v, "pemetaan_massal.xlsx", "Pemetaan", FMT_MASSAL)


with tab_mas:
    tampil_massal()

with tab_prodi:
    st.markdown(f"**{len(R.prodi):,}** program studi di **{len(R.ptn)}** PTN.".replace(",", "."))
    f1, f2, f3, f4, f5 = st.columns(5)
    p_f = f1.multiselect("PTN", R.ptn_list, key="p_ptn")
    j_f = f2.multiselect("Jenjang", sorted(R.prodi["jenjang"].unique()), key="p_jenjang")
    m_f = f3.multiselect("Mapel pendukung", R.mapel_semua, key="p_mapel")
    pv_f = f4.multiselect("Provinsi", sorted(R.prodi["provinsi"].dropna().unique()), key="p_prov")
    c_f = f5.text_input("Cari prodi", placeholder="mis. kedokteran", key="p_cari")
    d = R.prodi
    if p_f:
        d = d[d["ptn"].isin(p_f)]
    if j_f:
        d = d[d["jenjang"].isin(j_f)]
    if m_f:
        d = d[d["mapel_list"].apply(lambda L: bool(set(m_f).intersection(L)))]
    if pv_f:
        d = d[d["provinsi"].isin(pv_f)]
    if c_f:
        d = d[d["prodi"].str.contains(c_f, case=False, na=False)]
    st.caption(f"{len(d):,} prodi ditemukan.".replace(",", "."))
    out = d[["ptn", "prodi", "jenjang", "dt_2025", "peminat_2025", "dt_2026", "keketatan_prodi", "alumni_jur",
             "jenis_mapel", "provinsi", "kota"]].rename(columns={
        "ptn": "PTN", "prodi": "Program Studi", "jenjang": "Jenjang", "dt_2025": "DT 2025", "peminat_2025": "Peminat 2025",
        "dt_2026": "DT 2026", "keketatan_prodi": "Keketatan", "alumni_jur": "Alumni Jurusan",
        "jenis_mapel": "Mapel Pendukung", "provinsi": "Provinsi", "kota": "Kab/Kota"})
    st.dataframe(out, hide_index=True, height=560,
                 column_config={"Keketatan": st.column_config.NumberColumn(format="%.3f"),
                                "PTN": st.column_config.TextColumn(width="large"), "Program Studi": st.column_config.TextColumn(width="large"), "Mapel Pendukung": st.column_config.TextColumn(width="medium")})
    tombol_unduh(out, "data_prodi.xlsx", "Data Prodi", {"Keketatan": "0.000"})

with tab_ptn:
    f1, f2 = st.columns(2)
    pv = f1.multiselect("Provinsi", sorted(R.ptn["provinsi"].unique()), key="t_prov")
    cr = f2.text_input("Cari nama PTN", key="t_cari")
    t = R.ptn
    if pv:
        t = t[t["provinsi"].isin(pv)]
    if cr:
        t = t[t["ptn"].str.contains(cr, case=False, na=False)]
    st.caption(f"{len(t)} PTN ditemukan.")
    out = t.rename(columns={"ptn": "Nama PTN", "jumlah_prodi": "Jumlah Prodi", "dt_2025": "DT 2025",
                            "peminat_2025": "Peminat 2025", "dt_2026": "DT 2026", "keketatan_kampus": "Keketatan Kampus",
                            "alumni_ptn": "Alumni PTN", "provinsi": "Provinsi", "kota": "Kab/Kota"})
    st.dataframe(out, hide_index=True, height=560,
                 column_config={"Keketatan Kampus": st.column_config.NumberColumn(format="%.4f")})
    tombol_unduh(out, "data_ptn.xlsx", "Data PTN", {"Keketatan Kampus": "0.0000"})
