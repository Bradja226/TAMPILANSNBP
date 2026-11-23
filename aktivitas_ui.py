"""Tampilan 'Aktivitas terbaru': siapa mengubah apa, kapan (dipakai lihat.py)."""
import pandas as pd
import streamlit as st

import storage

IKON_JENIS = {"pilihan": "🎯", "nilai": "✏️", "keterangan": "📝", "rekomendasi": "📌", "impor": "📥"}
NAMA_JENIS = {"pilihan": "Pilihan PTN/prodi", "nilai": "Nilai pendukung", "keterangan": "Keterangan",
              "rekomendasi": "Daftar rekomendasi", "impor": "Impor massal"}


def _sekarang_wib():
    return pd.Timestamp.now(tz="UTC").tz_localize(None) + pd.Timedelta(hours=7)


def relatif(t, now):
    if pd.isna(t):
        return ""
    d = (now - t).total_seconds()
    if d < 60:
        return "baru saja"
    if d < 3600:
        return f"{int(d // 60)} menit lalu"
    if d < 86400:
        return f"{int(d // 3600)} jam lalu"
    return f"{int(d // 86400)} hari lalu"


def siapkan(R, ev):
    """List aktivitas -> DataFrame dengan nama siswa, kelas, dan waktu."""
    df = pd.DataFrame(ev)
    info = R.siswa.set_index("no")
    df["t"] = pd.to_datetime(df["waktu"], errors="coerce")
    df["Siswa"] = [info.loc[n, "nama"].title() if n in info.index else ("Sistem" if n == 0 else f"Siswa #{n}") for n in df["no"]]
    df["Kelas"] = [info.loc[n, "kelas"] if n in info.index else "" for n in df["no"]]
    df["Jenis"] = df["jenis"].map(lambda j: NAMA_JENIS.get(j, j))
    return df


def render_aktivitas(R, key):
    try:
        ev = storage.baca_aktivitas()
    except Exception as e:  # noqa: BLE001
        st.error(f"⚠️ Gagal membaca aktivitas: {e}")
        return
    if not ev:
        st.info("Belum ada aktivitas tercatat. Perubahan yang dilakukan di aplikasi Edit (memilih atau mengganti pilihan, "
                "mengisi keterangan, menyimpan daftar rekomendasi) akan muncul di sini.")
        return
    df = siapkan(R, ev)
    now = _sekarang_wib()
    hari_ini = df[df["t"].dt.date == now.date()]
    k1, k2, k3 = st.columns(3)
    k1.metric("Perubahan hari ini", len(hari_ini))
    k2.metric("Siswa berubah hari ini", int(hari_ini[hari_ini["no"] > 0]["no"].nunique()))
    k3.metric("Perubahan terakhir", relatif(df["t"].max(), now) or "-")

    st.markdown("#### Terbaru")
    for r in df.head(12).itertuples():
        nama = f"**{r.Siswa}**" + (f" ({r.Kelas})" if r.Kelas else "")
        st.markdown(f"{IKON_JENIS.get(r.jenis, '•')} {nama} {r.ringkas} &nbsp;·&nbsp; _{relatif(r.t, now)}_")

    st.markdown("#### Semua riwayat")
    f1, f2, f3 = st.columns(3)
    jenis_f = f1.multiselect("Jenis", sorted(df["Jenis"].unique()), key=f"akt_{key}_jenis")
    kelas_f = f2.multiselect("Kelas", sorted(k for k in df["Kelas"].unique() if k), key=f"akt_{key}_kelas")
    cari = f3.text_input("Cari nama siswa / kata kunci", key=f"akt_{key}_cari")
    v = df
    if jenis_f:
        v = v[v["Jenis"].isin(jenis_f)]
    if kelas_f:
        v = v[v["Kelas"].isin(kelas_f)]
    if cari:
        v = v[v["Siswa"].str.contains(cari, case=False, na=False, regex=False) | v["ringkas"].str.contains(cari, case=False, na=False, regex=False)]
    out = pd.DataFrame({"Waktu (WIB)": v["waktu"], "Kapan": [relatif(t, now) for t in v["t"]], "Siswa": v["Siswa"], "Kelas": v["Kelas"],
                        "Jenis": v["Jenis"], "Aktivitas": v["ringkas"]}).reset_index(drop=True)
    st.caption(f"{len(out)} aktivitas ditampilkan (maksimal {storage.AKT_MAKS} terbaru).")
    st.dataframe(out, hide_index=True, height=420, column_config={
        "Aktivitas": st.column_config.TextColumn(width="large"), "Siswa": st.column_config.TextColumn(width="medium")})
