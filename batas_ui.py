"""Tampilan 'Pemantau batas pendaftar per PTN' (dipakai app.py dan lihat.py)."""
import plotly.graph_objects as go
import streamlit as st

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
