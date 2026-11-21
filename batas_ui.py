"""Tampilan 'Pemantau batas pendaftar per PTN' (dipakai app.py dan lihat.py)."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import model as m

BATAS_TIDAK_ADA = "Data batas PTN belum ada (data/batas_ptn.csv)."


def render_pemantau(R, per_ptn, elim, key):
    st.subheader("🚦 Pemantau batas pendaftar per PTN")
    if not R.batas:
        st.info(BATAS_TIDAK_ADA)
        return
    if per_ptn.empty:
        st.info("Belum ada pilihan siswa yang tersimpan, jadi belum ada yang dipantau.")
        return
    lewat = per_ptn[per_ptn["Melebihi"] > 0]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("PTN yang dipilih", len(per_ptn))
    k2.metric("🔴 PTN melebihi batas", len(lewat))
    k3.metric("🟠 PTN penuh / hampir penuh", int(per_ptn["Status"].isin(["🟠 Penuh", "🟡 Hampir penuh"]).sum()))
    k4.metric("Siswa harus ganti pilihan", len(elim))
    st.caption("Pendaftar = jumlah siswa yang memilih PTN itu (Pilihan 1 atau 2). Jika melebihi batas, yang dieliminasi adalah "
               "siswa dengan **peluang paling kecil** di PTN tersebut.")
    top = per_ptn.sort_values("Terdaftar", ascending=False).head(12).iloc[::-1]
    fig = go.Figure([go.Bar(name="Batas", y=top["PTN"], x=top["Batas"].fillna(0), orientation="h", marker_color="rgba(148,163,184,.55)"),
                     go.Bar(name="Terdaftar", y=top["PTN"], x=top["Terdaftar"], orientation="h",
                            marker_color=["#dc2626" if m_ > 0 else "#2563eb" for m_ in top["Melebihi"]])])
    fig.update_layout(barmode="group", height=max(260, 34 * len(top) + 80), title="Pendaftar vs batas (12 PTN terpadat)",
                      yaxis_title=None, legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, key=f"pem_chart_{key}")
    st.dataframe(per_ptn, hide_index=True, height=min(420, 40 + 36 * len(per_ptn)), column_config={
        "PTN": st.column_config.TextColumn(width="large"),
        "Batas": st.column_config.NumberColumn(format="%d"), "Sisa": st.column_config.NumberColumn(format="%d"),
        "Melebihi": st.column_config.NumberColumn(format="%d")})
    with st.expander(f"⚠️ Siswa yang melebihi batas ({len(elim)}) — urut dari peluang terkecil"):
        if elim.empty:
            st.success("Tidak ada siswa yang melebihi batas.")
        else:
            st.dataframe(elim, hide_index=True, height=min(420, 40 + 36 * len(elim)), column_config={
                "PTN": st.column_config.TextColumn(width="large"), "Nama Siswa": st.column_config.TextColumn(width="medium"),
                "Peluang (%)": st.column_config.NumberColumn(format="%.1f"), "Batas": st.column_config.NumberColumn(format="%d")})


FMT_BATAS = {"Keketatan Kampus (%)": "0.0", "Daya Tampung 2026": "#,##0"}


def render_daftar_batas(R, per_ptn, key):
    """Daftar batas SEMUA PTN (tampil walau belum ada yang memilih). Mengembalikan tabel yang sedang tampil (untuk unduhan)."""
    if not R.batas or R.batas_df is None:
        st.info(BATAS_TIDAK_ADA)
        return None
    d = m.tabel_batas(R, per_ptn)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Jumlah PTN", len(d))
    k2.metric("Total batas (kursi pilihan)", f"{int(d['batas'].sum()):,}".replace(",", "."))
    k3.metric("🟢 Masih longgar", int((d["status"] == "🟢 Longgar").sum()))
    k4.metric("🔴 / 🟠 Penuh atau melebihi", int(d["status"].isin(["🔴 Melebihi", "🟠 Penuh"]).sum()))
    st.caption("**Batas** = jumlah maksimal siswa yang boleh memilih PTN itu (Pilihan 1 atau 2). **Terdaftar** = siswa yang saat ini sudah "
               "memilihnya. **Sisa** = batas dikurangi terdaftar. Jika melebihi batas, siswa dengan peluang paling kecil yang diminta mengganti pilihan.")
    f1, f2, f3 = st.columns(3)
    cari = f1.text_input("Cari nama PTN", key=f"bd_cari_{key}", placeholder="mis. bogor, indonesia")
    prov = f2.multiselect("Provinsi", sorted(d["provinsi"].dropna().unique()), key=f"bd_prov_{key}")
    tingkat = f3.multiselect("Tingkat", sorted(d["tingkat"].unique()), key=f"bd_tk_{key}",
                             help="A–E: ada alumni sekolah. F–G: belum ada alumni (dekat / di Jawa). H: jauh.")
    c1, c2 = st.columns(2)
    sisa_saja = c1.checkbox("Hanya yang masih ada sisa kursi", key=f"bd_sisa_{key}")
    terpilih = c2.checkbox("Hanya yang sudah ada pendaftar", key=f"bd_pilih_{key}")
    if cari:
        d = d[d["ptn"].str.contains(cari, case=False, na=False, regex=False)]
    if prov:
        d = d[d["provinsi"].isin(prov)]
    if tingkat:
        d = d[d["tingkat"].isin(tingkat)]
    if sisa_saja:
        d = d[d["sisa"] > 0]
    if terpilih:
        d = d[d["terdaftar"] > 0]
    out = pd.DataFrame({
        "Tingkat": d["tingkat"], "Nama PTN": d["ptn"], "Provinsi": d["provinsi"], "Batas Maksimal": d["batas"],
        "Terdaftar": d["terdaftar"], "Sisa": d["sisa"], "Status": d["status"], "Alumni Sekolah": d["alumni_ptn"].astype(int),
        "Lolos 2026": d["lolos_2026"].astype(int), "Daya Tampung 2026": d["dt_2026"], "Keketatan Kampus (%)": d["keketatan_kampus"] * 100,
        "Dasar Batas": d["alasan"]}).reset_index(drop=True)
    st.caption(f"{len(out)} PTN ditampilkan.")
    st.dataframe(out, hide_index=True, height=560, column_config={
        "Nama PTN": st.column_config.TextColumn(width="large"), "Dasar Batas": st.column_config.TextColumn(width="large"),
        "Batas Maksimal": st.column_config.NumberColumn(format="%d"), "Terdaftar": st.column_config.NumberColumn(format="%d"),
        "Sisa": st.column_config.NumberColumn(format="%d"), "Daya Tampung 2026": st.column_config.NumberColumn(format="%d"),
        "Keketatan Kampus (%)": st.column_config.NumberColumn(format="%.1f")})
    return out
