"""Dashboard interaktif Rasionalisasi SNBP 2027 (Streamlit)."""
import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import model as m

st.set_page_config(page_title="Rasionalisasi SNBP 2027", page_icon="🎓", layout="wide")

WARNA = {"AMAN": "#16a34a", "KOMPETITIF": "#f59e0b", "BERISIKO": "#dc2626"}
IKON = {"AMAN": "🟢", "KOMPETITIF": "🟡", "BERISIKO": "🔴", "": ""}
SARAN_ZONA = {
    "AMAN": "Peluang tinggi. Layak dikunci sebagai target utama.",
    "KOMPETITIF": "Peluang terbuka. Wajib di Pilihan 1, dan Pilihan 2 diisi zona AMAN.",
    "BERISIKO": "Sebagian besar kandidat gagal. Pertimbangkan prodi pada tab Rekomendasi.",
}
PIL_FILE = m.DATA / "pilihan_siswa.csv"

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem;}
    .badge {display:inline-block; padding:.15rem .7rem; border-radius:999px; color:#fff;
            font-weight:700; font-size:.85rem; letter-spacing:.03em;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Memuat database PTN & prodi…")
def muat_ref():
    return m.Ref()


R = muat_ref()


def badge(s):
    return f'<span class="badge" style="background:{WARNA[s]}">{s}</span>' if s else ""


def pct(x):
    return "–" if x is None or pd.isna(x) else f"{x * 100:.1f}%"


# ------------------------------------------------------------------ penyimpanan pilihan siswa
def init_state():
    if "pilihan" in st.session_state:
        return
    data = {}
    if PIL_FILE.exists():
        try:
            for r in pd.read_csv(PIL_FILE).to_dict("records"):
                data[int(r["no"])] = {k: (None if pd.isna(v) else v) for k, v in r.items() if k != "no"}
        except Exception:
            pass
    st.session_state["pilihan"] = data


def simpan_disk():
    rows = [{"no": k, **v} for k, v in st.session_state["pilihan"].items()]
    try:
        pd.DataFrame(rows, columns=m.PIL_COLS).to_csv(PIL_FILE, index=False)
    except OSError:
        st.warning("Tidak bisa menulis ke disk (server read-only). Data hanya tersimpan selama sesi ini.")


init_state()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🎓 SNBP 2027")
    st.caption("Rasionalisasi pilihan PTN & prodi berbasis model regresi logistik")
    opsi_siswa = R.siswa["no"].astype(int).tolist()
    info = R.siswa.set_index("no")
    no = st.selectbox(
        "Pilih siswa", opsi_siswa,
        format_func=lambda n: f"{n:03d} · {info.loc[n, 'nama']} ({info.loc[n, 'kelas']})",
        help="Ketik untuk mencari nama siswa.",
    )
    SIS = R.siswa[R.siswa["no"] == no].iloc[0]

    with st.expander("⚙️ Ambang batas zona"):
        cut_a = st.number_input("AMAN ≥ (%)", 0.0, 100.0, float(R.params["cut_aman"] * 100), 0.1) / 100
        cut_k = st.number_input("KOMPETITIF ≥ (%)", 0.0, 100.0, float(R.params["cut_kompetitif"] * 100), 0.1) / 100
        if cut_k > cut_a:
            st.error("Batas KOMPETITIF tidak boleh lebih besar dari AMAN.")
            cut_k = cut_a
        st.caption("Default = nilai di sheet Parameter_Model. Di bawah KOMPETITIF = BERISIKO.")
    st.divider()
    st.caption("Pilihan siswa disimpan di `data/pilihan_siswa.csv`.")

st.title("Rasionalisasi SNBP 2027")
tab_kalk, tab_rek, tab_mas, tab_model, tab_ref = st.tabs(
    ["🎯 Kalkulator Siswa", "🔍 Rekomendasi Prodi", "👥 Pemetaan Massal", "📈 Model & Validasi", "📚 Database PTN & Prodi"]
)


# ================================================================== TAB 1 — KALKULATOR
def gauge(pr, stat, judul):
    mx = max(0.3, min(1.0, np.ceil(pr * 1.25 * 10) / 10), cut_a * 1.5)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=pr * 100, number={"suffix": "%", "valueformat": ".1f"},
        title={"text": judul},
        gauge={"axis": {"range": [0, mx * 100]}, "bar": {"color": WARNA[stat], "thickness": .3},
               "steps": [{"range": [0, cut_k * 100], "color": "rgba(220,38,38,.22)"},
                         {"range": [cut_k * 100, cut_a * 100], "color": "rgba(245,158,11,.30)"},
                         {"range": [cut_a * 100, mx * 100], "color": "rgba(22,163,74,.22)"}]}))
    fig.update_layout(height=230, margin=dict(l=25, r=25, t=55, b=5))
    return fig


def blok_pilihan(k, judul, saved):
    """Form satu pilihan. Mengembalikan (ptn, prodi, nilai_pendukung_rata2)."""
    st.subheader(judul)
    ptn_s = saved.get(f"ptn{k}")
    ptn = st.selectbox(
        "PTN tujuan", R.ptn_list, key=f"ptn{k}_{no}", placeholder="Pilih PTN…",
        index=R.ptn_list.index(ptn_s) if ptn_s in R.ptn_list else None)
    if not ptn:
        return None, None, None
    opsi = R.prodi_opsi[ptn]
    prodi_s = saved.get(f"prodi{k}") if ptn_s == ptn else None
    prodi = st.selectbox(
        "Program studi", opsi, key=f"prodi{k}_{no}_{ptn}", placeholder="Pilih program studi…",
        index=opsi.index(prodi_s) if prodi_s in opsi else None)
    if not prodi:
        return ptn, None, None
    row = R.idx[(ptn, prodi)]
    mapel = row["mapel_list"] or ["Nilai pendukung"]
    if prodi_s == prodi and saved.get(f"nilai{k}") is not None:
        default = float(saved[f"nilai{k}"])
    elif pd.notna(SIS.get(f"pend_p{k}")):
        default = float(SIS[f"pend_p{k}"])
    else:
        default = float(SIS["rata_rata"])
    st.caption(f"Mapel pendukung: **{row['jenis_mapel']}** — isi nilai rapor masing-masing mapel:")
    cols = st.columns(len(mapel))
    nilai = [c.number_input(mp, 0.0, 100.0, default, 0.5, key=f"nm{k}_{no}_{ptn}_{prodi}_{i}")
             for i, (c, mp) in enumerate(zip(cols, mapel))]
    return ptn, prodi, float(np.mean(nilai))


def kartu_hasil(res, judul):
    gx, ix = st.columns([1, 1])
    gx.plotly_chart(gauge(res["p"], res["status"], judul), key=f"g_{judul}_{no}")
    ix.markdown(f"#### {badge(res['status'])}", unsafe_allow_html=True)
    ix.caption(SARAN_ZONA[res["status"]])
    row = res["row"]
    ix.metric("Daya tampung 2026", f"{int(row['dt_2026']):,}".replace(",", "."))
    c1, c2, c3 = st.columns(3)
    c1.metric("Keketatan prodi (DT/peminat)", f"{row['keketatan_prodi'] * 100:.1f}%")
    c2.metric("Alumni di PTN", int(row["alumni_ptn"]))
    c3.metric("Alumni di jurusan", int(row["alumni_jur"]))
    if row["keketatan_prodi"] > 1:
        st.warning("Daya tampung prodi ini lebih besar dari jumlah peminat 2025 (keketatan > 100%). "
                   "Kemungkinan prodi baru / data peminat belum lengkap — hasil model bisa terlalu optimistis.")


with tab_kalk:
    saved = st.session_state["pilihan"].get(int(no), {})
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Nama", SIS["nama"].title())
    h2.metric("Kelas", SIS["kelas"])
    h3.metric("Rata-rata rapor", f"{SIS['rata_rata']:.2f}")
    h4.metric("Nilai komposit", f"{SIS['nilai_komposit']:.3f}")
    st.divider()

    kiri, kanan = st.columns(2, gap="large")
    with kiri:
        ptn1, prodi1, nilai1 = blok_pilihan("1", "Pilihan 1 (prioritas utama)", saved)
    with kanan:
        ptn2, prodi2, nilai2 = blok_pilihan("2", "Pilihan 2 (cadangan / strategis)", saved)

    r1 = m.evaluasi(R, SIS, ptn1, prodi1, nilai1, 0, cut_a, cut_k)
    r2 = m.evaluasi(R, SIS, ptn2, prodi2, nilai2, 1, cut_a, cut_k)
    st.divider()
    if not r1 and not r2:
        st.info("Pilih PTN dan program studi di atas untuk melihat peluang kelolosan.")
    else:
        kiri, kanan = st.columns(2, gap="large")
        with kiri:
            if r1:
                kartu_hasil(r1, "Peluang Pilihan 1")
        with kanan:
            if r2:
                kartu_hasil(r2, "Peluang Pilihan 2")

        if r1:
            gab = m.gabungan(r1["p"], r2["p"] if r2 else None)
            saran = m.strategi(r1["status"], r2["status"] if r2 else "")
            st.markdown("### Evaluasi kombinasi")
            g1, g2 = st.columns([1, 2])
            g1.metric("Peluang minimal 1 lolos", pct(gab))
            kotak = {"Kombinasi Ideal (Ada Opsi Aman)": st.success, "Perlu Pengaman di Pilihan 2": st.warning,
                     "Evaluasi Ulang Kedua Pilihan": st.error}.get(saran, st.info)
            with g2:
                kotak(f"**{saran}**")

        with st.expander("🧮 Rincian perhitungan (kontribusi tiap faktor ke logit)"):
            for judul, res in (("Pilihan 1", r1), ("Pilihan 2", r2)):
                if res:
                    st.markdown(f"**{judul}** — logit z = {res['z']:.3f} → peluang = {pct(res['p'])}")
                    st.dataframe(m.kontribusi(*res["args"]), hide_index=True,
                                 column_config={"Nilai": st.column_config.NumberColumn(format="%.3f"),
                                                "Beta": st.column_config.NumberColumn(format="%.4f"),
                                                "Kontribusi": st.column_config.NumberColumn(format="%.3f")})

        b1, b2, _ = st.columns([1.2, 1.2, 3])
        if b1.button("💾 Simpan ke Pemetaan Massal", type="primary", disabled=r1 is None):
            st.session_state["pilihan"][int(no)] = {
                "ptn1": ptn1, "prodi1": prodi1, "nilai1": nilai1,
                "ptn2": ptn2 if r2 else None, "prodi2": prodi2 if r2 else None, "nilai2": nilai2 if r2 else None}
            simpan_disk()
            st.toast("Pilihan siswa tersimpan ✅")
        if int(no) in st.session_state["pilihan"] and b2.button("🗑️ Hapus pilihan tersimpan"):
            del st.session_state["pilihan"][int(no)]
            simpan_disk()
            st.rerun()


# ================================================================== TAB 2 — REKOMENDASI
with tab_rek:
    st.markdown("Menyaring seluruh prodi yang punya **minimal 1 mapel pendukung yang sama** dengan pilihan siswa, "
                "lengkap dengan peluang & statusnya.")
    c1, c2 = st.columns(2)
    sumber = c1.radio("Mapel pendukung diambil dari", ["Pilihan 1", "Pilihan 2"], horizontal=True)
    res_src = r1 if sumber == "Pilihan 1" else r2
    mapel_def = res_src["row"]["mapel_list"] if res_src else []
    kunci = f"{no}_{sumber}_{res_src['row']['ptn'] if res_src else ''}_{res_src['row']['prodi'] if res_src else ''}"
    acuan = c1.multiselect("Mata pelajaran acuan", R.mapel_semua, default=mapel_def, key=f"acuan_{kunci}",
                           help="Otomatis terisi dari prodi yang dipilih di Kalkulator; bisa diubah bebas.")
    nilai_rek = c2.number_input("Rata-rata nilai mapel pendukung", 0.0, 100.0,
                                float(res_src["nilai"]) if res_src else float(SIS["rata_rata"]), 0.5,
                                key=f"nilrek_{kunci}")
    status_filter = c2.radio("Filter status", ["AMAN saja", "AMAN + KOMPETITIF", "Semua"], horizontal=True)

    if not acuan:
        st.info("Pilih minimal satu mata pelajaran acuan (atau pilih prodi di tab Kalkulator).")
    else:
        sembunyi = st.checkbox("Sembunyikan prodi dengan keketatan > 100% (data tidak wajar)", value=True,
                               help="Prodi yang daya tampungnya melebihi peminat (umumnya prodi baru) membuat model "
                                    "memberi peluang ≈ 100%. Matikan centang untuk menampilkan semuanya seperti di Excel.")
        dr, n_an = m.rekomendasi(R, SIS, acuan, nilai_rek, cut_a, cut_k, sembunyi)
        kol_st = "status1" if sumber == "Pilihan 1" else "status2"
        kol_p = "p1" if sumber == "Pilihan 1" else "p2"
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Prodi linier ditemukan", f"{len(dr):,}".replace(",", "."))
        for kc, s in zip((k2, k3, k4), ("AMAN", "KOMPETITIF", "BERISIKO")):
            kc.metric(f"{IKON[s]} {s}", int((dr[kol_st] == s).sum()))
        if sembunyi and n_an:
            st.caption(f"{n_an} prodi disembunyikan karena keketatan > 100%.")

        f1, f2, f3, f4 = st.columns(4)
        jenjang = f1.multiselect("Jenjang", sorted(dr["jenjang"].unique()))
        prov = f2.multiselect("Provinsi", sorted(dr["provinsi"].dropna().unique()))
        ptn_f = f3.multiselect("PTN", sorted(dr["ptn"].unique()))
        cari = f4.text_input("Cari nama prodi", placeholder="mis. teknik, pendidikan")

        if status_filter == "AMAN saja":
            dr = dr[dr[kol_st] == "AMAN"]
        elif status_filter == "AMAN + KOMPETITIF":
            dr = dr[dr[kol_st].isin(["AMAN", "KOMPETITIF"])]
        if jenjang:
            dr = dr[dr["jenjang"].isin(jenjang)]
        if prov:
            dr = dr[dr["provinsi"].isin(prov)]
        if ptn_f:
            dr = dr[dr["ptn"].isin(ptn_f)]
        if cari:
            dr = dr[dr["prodi"].str.contains(cari, case=False, na=False)]
        dr = dr.sort_values(kol_p, ascending=False)

        out = pd.DataFrame({
            "Nama PTN": dr["ptn"], "Program Studi": dr["prodi"], "Mapel Pendukung": dr["jenis_mapel"],
            "DT 2026": dr["dt_2026"], "Keketatan Prodi (%)": dr["keketatan_prodi"] * 100,
            "Peluang P1 (%)": dr["p1"] * 100, "Status P1": dr["status1"].map(lambda s: f"{IKON[s]} {s}"),
            "Peluang P2 (%)": dr["p2"] * 100, "Status P2": dr["status2"].map(lambda s: f"{IKON[s]} {s}"),
            "Provinsi": dr["provinsi"], "Kab/Kota": dr["kota"]})
        st.caption(f"Menampilkan **{len(out):,}** prodi, diurutkan dari peluang tertinggi ({sumber}). "
                   "Klik judul kolom untuk mengurutkan ulang.".replace(",", "."))
        st.dataframe(out, hide_index=True, height=520, column_config={
            "Keketatan Prodi (%)": st.column_config.NumberColumn(format="%.1f"),
            "Peluang P1 (%)": st.column_config.NumberColumn(format="%.1f"),
            "Peluang P2 (%)": st.column_config.NumberColumn(format="%.1f"),
            "DT 2026": st.column_config.NumberColumn(format="%d")})
        st.download_button("⬇️ Unduh hasil (CSV)", out.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"rekomendasi_{SIS['nama'].replace(' ', '_')}.csv", mime="text/csv")


# ================================================================== TAB 3 — PEMETAAN MASSAL
def to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Pemetaan")
    return buf.getvalue()


with tab_mas:
    tb = m.tabel_massal(R, st.session_state["pilihan"], cut_a, cut_k)
    terpetakan = tb[tb["Peluang P1"].notna()]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total siswa", len(tb))
    k2.metric("Sudah dipetakan", len(terpetakan), f"{len(terpetakan) / len(tb) * 100:.0f}%", delta_color="off")
    k3.metric("🟢 Pilihan 1 AMAN", int((tb["Status P1"] == "AMAN").sum()))
    k4.metric("🔴 Perlu evaluasi ulang", int((tb["Saran Strategi"] == "Evaluasi Ulang Kedua Pilihan").sum()))

    if len(terpetakan):
        g1, g2 = st.columns(2)
        sc = terpetakan["Saran Strategi"].value_counts().reset_index()
        sc.columns = ["Strategi", "Jumlah"]
        g1.plotly_chart(px.bar(sc, x="Jumlah", y="Strategi", orientation="h", title="Saran strategi kombinasi",
                               color="Strategi", color_discrete_map={
                                   "Kombinasi Ideal (Ada Opsi Aman)": "#16a34a", "Perlu Pengaman di Pilihan 2": "#f59e0b",
                                   "Evaluasi Ulang Kedua Pilihan": "#dc2626", "Isi Pilihan 2 sebagai pengaman": "#64748b"})
                        .update_layout(showlegend=False, height=300, yaxis_title=None), key="g_strat")
        st_df = pd.concat([terpetakan["Status P1"].value_counts().rename("Pilihan 1"),
                           terpetakan["Status P2"].replace("", np.nan).value_counts().rename("Pilihan 2")], axis=1
                          ).reindex(["AMAN", "KOMPETITIF", "BERISIKO"]).fillna(0).reset_index(names="Status")
        fig = go.Figure([go.Bar(name=c, x=st_df["Status"], y=st_df[c]) for c in ("Pilihan 1", "Pilihan 2")])
        fig.update_layout(barmode="group", title="Sebaran status", height=300)
        g2.plotly_chart(fig, key="g_status")

    f1, f2, f3, f4 = st.columns(4)
    kelas_f = f1.multiselect("Kelas", sorted(tb["Kelas"].unique()))
    strat_f = f2.multiselect("Saran strategi", sorted(x for x in tb["Saran Strategi"].unique() if x))
    cari = f3.text_input("Cari nama siswa")
    hanya = f4.checkbox("Hanya yang sudah dipetakan")
    v = tb.copy()
    if kelas_f:
        v = v[v["Kelas"].isin(kelas_f)]
    if strat_f:
        v = v[v["Saran Strategi"].isin(strat_f)]
    if cari:
        v = v[v["Nama Siswa"].str.contains(cari, case=False, na=False)]
    if hanya:
        v = v[v["Peluang P1"].notna()]

    tampil = v.copy()
    for c in ("Peluang P1", "Peluang P2", "Peluang Min. 1 Lolos"):
        tampil[c] = tampil[c] * 100
    for c in ("Status P1", "Status P2"):
        tampil[c] = tampil[c].map(lambda s: f"{IKON[s]} {s}" if s else "")
    st.dataframe(tampil, hide_index=True, height=480, column_config={
        "Nilai Komposit": st.column_config.NumberColumn(format="%.2f"),
        "Nilai Pendukung P1": st.column_config.NumberColumn(format="%.2f"),
        "Nilai Pendukung P2": st.column_config.NumberColumn(format="%.2f"),
        "Peluang P1": st.column_config.NumberColumn("Peluang P1 (%)", format="%.1f"),
        "Peluang P2": st.column_config.NumberColumn("Peluang P2 (%)", format="%.1f"),
        "Peluang Min. 1 Lolos": st.column_config.NumberColumn("Peluang min. 1 lolos (%)", format="%.1f")})
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("⬇️ Unduh Excel", to_excel(v), file_name="pemetaan_massal_snbp_2027.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("⬇️ Unduh CSV", v.to_csv(index=False).encode("utf-8-sig"),
                       file_name="pemetaan_massal_snbp_2027.csv", mime="text/csv")

    with st.expander("📥 Impor pilihan banyak siswa sekaligus (CSV / Excel)"):
        st.markdown("Unduh templat, isi kolom PTN & Prodi (harus sama dengan nama di database), lalu unggah kembali. "
                    "Nilai pendukung boleh dikosongkan → otomatis memakai rata-rata rapor siswa.")
        tmpl = pd.DataFrame({c: [""] * len(R.siswa) for c in m.TEMPLATE_COLS})
        tmpl["Nama Siswa"] = R.siswa["nama"].values
        st.download_button("⬇️ Unduh templat", tmpl.to_csv(index=False).encode("utf-8-sig"),
                           file_name="templat_pilihan_siswa.csv", mime="text/csv")
        up = st.file_uploader("Unggah file", type=["csv", "xlsx"])
        if up is not None and st.button("Proses impor"):
            try:
                dfi = pd.read_excel(up) if up.name.lower().endswith("xlsx") else pd.read_csv(up)
                hasil, errs = m.impor_pilihan(R, dfi)
                st.session_state["pilihan"].update(hasil)
                simpan_disk()
                st.success(f"{len(hasil)} siswa berhasil diimpor.")
                if errs:
                    st.warning("Sebagian baris dilewati:\n\n" + "\n".join(f"- {e}" for e in errs[:30]))
            except Exception as e:  # noqa: BLE001
                st.error(f"Gagal membaca file: {e}")


# ================================================================== TAB 4 — MODEL & VALIDASI
with tab_model:
    P = R.params
    st.markdown("Model **regresi logistik (Bayesian MAP)** dikalibrasi pada data pemetaan SNBP 2026 SMAN 1 Ciampea.")
    nama = {"intercept": "Intercept (konstanta)", "nilai": "Nilai komposit", "pendukung": "Mapel pendukung (0–100)",
            "alumni_ptn": "Alumni di PTN", "alumni_jur": "Alumni di jurusan",
            "keketatan_prodi": "Keketatan prodi (%)", "keketatan_kampus": "Keketatan kampus (%)",
            "pilihan_2": "Pilihan ke-2 (penalti)"}
    tp = pd.DataFrame({"Variabel": list(nama.values()), "Beta": [P[k] for k in nama],
                       "Odds ratio": [np.exp(P[k]) for k in nama]})
    c1, c2 = st.columns([3, 2])
    c1.dataframe(tp, hide_index=True, column_config={"Beta": st.column_config.NumberColumn(format="%.6f"),
                                                      "Odds ratio": st.column_config.NumberColumn(format="%.4f")})
    c2.markdown("**Ambang zona (dipakai sekarang)**")
    c2.markdown(f"- {IKON['AMAN']} AMAN ≥ **{cut_a * 100:.2f}%**\n"
                f"- {IKON['KOMPETITIF']} KOMPETITIF ≥ **{cut_k * 100:.2f}%**\n"
                f"- {IKON['BERISIKO']} BERISIKO < {cut_k * 100:.2f}%")

    H = R.hist.copy()
    z = m.logit(P, H["nilai"], H["pendukung"], H["alumni_ptn"], H["alumni_jur"], H["keketatan_prodi"],
                H["keketatan_kampus"], (H["pilihan_ke"] == 2).astype(int))
    H["peluang"] = m.prob(z)
    H["zona"] = m.status(H["peluang"], cut_a, cut_k)
    y = (H["aktual"] == "YA").astype(int)
    st.markdown("### Validasi pada data historis")
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Jumlah data", len(H))
    v2.metric("Lolos aktual", int(y.sum()))
    v3.metric("ROC-AUC (dihitung ulang)", f"{m.auc(y, H['peluang']):.4f}")
    v4.metric("Brier score", f"{np.mean((H['peluang'] - y) ** 2):.4f}")
    g1, g2 = st.columns(2)
    ct = pd.crosstab(H["zona"], H["aktual"]).reindex(["AMAN", "KOMPETITIF", "BERISIKO"]).fillna(0).astype(int)
    g1.markdown("**Zona model vs hasil aktual**")
    g1.dataframe(ct)
    H["Hasil aktual"] = H["aktual"].map({"YA": "Lolos", "TIDAK": "Tidak lolos"})
    H["Peluang model (%)"] = H["peluang"] * 100
    g2.plotly_chart(px.box(H, x="Hasil aktual", y="Peluang model (%)", points="all",
                           title="Sebaran peluang model").update_layout(height=320), key="g_box")
    with st.expander("Lihat 198 data historis"):
        st.dataframe(H.drop(columns=["logit_excel", "peluang_excel", "zona_excel", "Hasil aktual", "Peluang model (%)"]), hide_index=True)


# ================================================================== TAB 5 — DATABASE
with tab_ref:
    st.markdown(f"Database **{len(R.ptn)} PTN** dan **{len(R.prodi):,} program studi**.".replace(",", "."))
    f1, f2, f3, f4 = st.columns(4)
    p_f = f1.multiselect("PTN ", R.ptn_list)
    j_f = f2.multiselect("Jenjang ", sorted(R.prodi["jenjang"].unique()))
    m_f = f3.multiselect("Mapel pendukung", R.mapel_semua)
    c_f = f4.text_input("Cari prodi ", placeholder="mis. kedokteran")
    d = R.prodi
    if p_f:
        d = d[d["ptn"].isin(p_f)]
    if j_f:
        d = d[d["jenjang"].isin(j_f)]
    if m_f:
        d = d[d["mapel_list"].apply(lambda L: bool(set(m_f).intersection(L)))]
    if c_f:
        d = d[d["prodi"].str.contains(c_f, case=False, na=False)]
    st.caption(f"{len(d):,} prodi ditemukan.".replace(",", "."))
    st.dataframe(d[["ptn", "prodi", "jenjang", "dt_2025", "peminat_2025", "dt_2026", "keketatan_prodi",
                    "alumni_jur", "jenis_mapel", "provinsi", "kota"]].rename(columns={
        "ptn": "PTN", "prodi": "Program Studi", "jenjang": "Jenjang", "dt_2025": "DT 2025",
        "peminat_2025": "Peminat 2025", "dt_2026": "DT 2026", "keketatan_prodi": "Keketatan",
        "alumni_jur": "Alumni Jurusan", "jenis_mapel": "Mapel Pendukung", "provinsi": "Provinsi", "kota": "Kab/Kota"}),
        hide_index=True, height=560, column_config={"Keketatan": st.column_config.NumberColumn(format="%.3f")})
