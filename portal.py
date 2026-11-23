"""PORTAL SISWA — halaman pribadi per siswa lewat tautan berkode (?k=...).
Hanya menampilkan data SATU siswa. Tanpa kode yang benar, tidak ada data yang tampil."""
import pandas as pd
import streamlit as st

import model as m
import batas_ui
import storage
import tautan
from exportxl import tombol_xlsx

st.set_page_config(page_title="Rekomendasi Prodi SNBP", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>.block-container{padding-top:2rem;max-width:1200px;}</style>", unsafe_allow_html=True)
IKON = {m.Z_BAIK: "🟢", m.Z_KOMP: "🟡", m.Z_RISIKO: "🔴", "": ""}
ARTI = {m.Z_BAIK: "peluang terbaik (± 4 dari 10 lolos pada data 2026)", m.Z_KOMP: "peluang terbuka (± 21% lolos), sebaiknya dipasangkan dengan pilihan peluang baik",
        m.Z_RISIKO: "peluang sangat kecil (± 2% lolos)"}


@st.cache_resource(show_spinner="Memuat data…")
def muat_ref():
    return m.Ref()


R = muat_ref()
CUT_A, CUT_K = R.params["cut_aman"], R.params["cut_kompetitif"]

st.title("🎓 Rekomendasi Prodi SNBP")
no = tautan.cari_siswa(st.query_params.get("k", ""), R.siswa)
if no is None:
    st.info("Tautan ini tidak valid atau sudah tidak berlaku. Silakan minta tautan pribadi kepada guru BK.")
    st.stop()

SIS = R.siswa[R.siswa["no"] == no].iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Nama", SIS["nama"].title())
c2.metric("Kelas", SIS["kelas"])
c3.metric("Nilai komposit", f"{SIS['nilai_komposit']:.2f}")


def _lst(s):
    return [x for x in str(s).split("|") if x]


def aman_baca(fn, default):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        st.error(f"⚠️ Gagal memuat data: {e}")
        return default


tab_rekom, tab_batas = st.tabs(["📌 Rekomendasi untuk kamu", "🚦 Batas pendaftar PTN"])

with tab_rekom:
    # ------------------------------------------------------------------ pilihan siswa saat ini
    rec_pil = aman_baca(storage.baca, {}).get(int(no))
    if rec_pil:
        baris = []
        for k, jud, p2 in (("1", "Pilihan 1", 0), ("2", "Pilihan 2", 1)):
            r = m.evaluasi(R, SIS, rec_pil.get(f"ptn{k}"), rec_pil.get(f"prodi{k}"), rec_pil.get(f"nilai{k}"), p2, CUT_A, CUT_K)
            if r:
                baris.append({"Pilihan": jud, "PTN": r["row"]["ptn"], "Program Studi": r["row"]["prodi"],
                              "Peluang (%)": r["p"] * 100, "Status": f"{IKON[r['status']]} {r['status']}"})
        if baris:
            st.subheader("Pilihan kamu saat ini")
            st.dataframe(pd.DataFrame(baris), hide_index=True, column_config={
                "Peluang (%)": st.column_config.NumberColumn(format="%.1f"),
                "PTN": st.column_config.TextColumn(width="large"), "Program Studi": st.column_config.TextColumn(width="large")})

    # ------------------------------------------------------------------ daftar rekomendasi
    st.subheader("Daftar rekomendasi untuk kamu")
    daftar = sorted([r for r in aman_baca(storage.baca_rek, []) if r["no"] == int(no)], key=lambda r: r["id"], reverse=True)
    if not daftar:
        st.info("Belum ada daftar rekomendasi. Guru BK akan menambahkannya — silakan cek lagi nanti.")


    def tampil_daftar(rec):
        acuan = _lst(rec["mapel"])
        d, _ = m.rekomendasi(R, SIS, acuan, rec["nilai"], CUT_A, CUT_K, bool(rec["sembunyi"]))
        d = m.saring_rek(d, rec["sumber"], rec["status_filter"], _lst(rec["jenjang"]), _lst(rec["provinsi"]),
                         _lst(rec["ptn"]), rec["cari"]).head(rec["batas"])
        st.caption(f"Mapel pendukung: **{', '.join(acuan) or '-'}** · nilai pendukung {rec['nilai']:.1f} · "
                   f"diurutkan menurut peluang sebagai **{rec['sumber']}** · filter: {m.nama_filter(rec['status_filter'])}")
        if rec["catatan"]:
            st.info(rec["catatan"])
        cari = st.text_input("Cari prodi / PTN di daftar ini", key=f"cari_{rec['id']}", placeholder="mis. teknik, IPB")
        if cari:
            d = d[d["prodi"].str.contains(cari, case=False, na=False, regex=False)
                  | d["ptn"].str.contains(cari, case=False, na=False, regex=False)]
        out = pd.DataFrame({
            "Nama PTN": d["ptn"], "Program Studi": d["prodi"], "Jenjang": d["jenjang"], "Daya Tampung 2026": d["dt_2026"],
            "Peluang P1 (%)": d["p1"] * 100, "Status P1": d["status1"].map(lambda s: f"{IKON[s]} {s}"),
            "Peluang P2 (%)": d["p2"] * 100, "Status P2": d["status2"].map(lambda s: f"{IKON[s]} {s}"),
            "Provinsi": d["provinsi"]})
        st.caption(f"{len(out)} prodi ditampilkan.")
        st.dataframe(out, hide_index=True, height=min(560, 40 + 36 * max(len(out), 3)), column_config={
            "Nama PTN": st.column_config.TextColumn(width="large"), "Program Studi": st.column_config.TextColumn(width="large"),
            "Daya Tampung 2026": st.column_config.NumberColumn(format="%d"),
            "Peluang P1 (%)": st.column_config.NumberColumn(format="%.1f"),
            "Peluang P2 (%)": st.column_config.NumberColumn(format="%.1f")})
        out_x = out.assign(**{"Status P1": d["status1"].values, "Status P2": d["status2"].values})
        tombol_xlsx("⬇️ Unduh daftar ini (Excel)", out_x, f"rekomendasi_{rec['id']}.xlsx", "Rekomendasi",
                    {"Peluang P1 (%)": "0.0", "Peluang P2 (%)": "0.0", "Daya Tampung 2026": "0"}, key=f"x_{rec['id']}")


    for i, rec in enumerate(daftar):
        with st.expander(f"📌 {rec['judul'] or 'Daftar rekomendasi'} · {rec['tanggal']}", expanded=(i == 0)):
            tampil_daftar(rec)

    with st.expander("ℹ️ Cara membaca tabel"):
        st.markdown(
            "- **Peluang P1** = perkiraan peluang lolos jika prodi itu kamu pilih sebagai **Pilihan 1**; **P2** jika sebagai **Pilihan 2** "
            "(Pilihan 2 punya peluang lebih rendah).\n"
            f"- 🟢 **{m.Z_BAIK}** (≥ {CUT_A * 100:.0f}%): {ARTI[m.Z_BAIK]}.\n"
            f"- 🟡 **{m.Z_KOMP}** (≥ {CUT_K * 100:.0f}%): {ARTI[m.Z_KOMP]}.\n"
            f"- 🔴 **{m.Z_RISIKO}** (< {CUT_K * 100:.0f}%): {ARTI[m.Z_RISIKO]}.\n"
            "- Angka ini **perkiraan** dari model yang dilatih pada data pemetaan SNBP 2026 SMAN 1 Ciampea. Ini bukan jaminan hasil seleksi — "
            "diskusikan pilihan akhir bersama guru BK dan orang tua.")


with tab_batas:
    st.markdown("Setiap PTN punya **batas jumlah siswa** sekolah kita yang boleh memilihnya, supaya pilihan tidak menumpuk di satu tempat. "
                "Cek **Sisa** sebelum menentukan pilihan. Jika sebuah PTN melebihi batas, siswa dengan peluang paling kecil di PTN itu "
                "akan diminta mengganti pilihan.")
    _pil_all = aman_baca(storage.baca, {})
    _tb = m.tabel_massal(R, _pil_all, CUT_A, CUT_K)
    _, _per_ptn, _ = m.analisis_batas(_tb, R.batas) if R.batas else ({}, pd.DataFrame(columns=m.KOLOM_PTN), None)
    batas_ui.render_daftar_batas(R, _per_ptn, "portal")
