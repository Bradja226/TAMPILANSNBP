"""
Ekstrak data dari workbook Excel Rasionalisasi SNBP menjadi file CSV/JSON di folder data/.
Jalankan ulang setiap kali Excel diperbarui (mis. nilai semester baru):

    python build_data.py "Rasionalisasi_SNBP_2027_Final.xlsx"

Nomor siswa TETAP walau peringkat berubah (lihat idsiswa.py). Peringkat dihitung ulang dari rata-rata rapor.
"""
import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from idsiswa import tetapkan_no

AKAR = Path(__file__).parent
SRC = sys.argv[1] if len(sys.argv) > 1 else next(iter(sorted(AKAR.glob("*.xlsx"))), None)
if SRC is None:
    sys.exit("Tidak ada file Excel. Jalankan: python build_data.py nama_file.xlsx")
OUT = AKAR / "data"
OUT.mkdir(exist_ok=True)

# ---------- Parameter model (nilai hasil, bukan formula) ----------
ws = load_workbook(SRC, data_only=True)["Parameter_Model"]
params = {
    "intercept": ws["C6"].value, "nilai": ws["C7"].value, "pendukung": ws["C8"].value,
    "alumni_ptn": ws["C9"].value, "alumni_jur": ws["C10"].value,
    "keketatan_prodi": ws["C11"].value, "keketatan_kampus": ws["C12"].value,
    "pilihan_2": ws["C13"].value,
    "cut_aman": ws["C18"].value, "cut_kompetitif": ws["C19"].value,
}
# Ambang zona: ditetapkan dari evaluasi data 2026 (bukan dari sel C18/C19 Excel). Ubah di sini bila perlu.
AMBANG_BAIK, AMBANG_KOMPETITIF = 0.30, 0.05
params["cut_aman_excel"], params["cut_kompetitif_excel"] = params["cut_aman"], params["cut_kompetitif"]
params["cut_aman"], params["cut_kompetitif"] = AMBANG_BAIK, AMBANG_KOMPETITIF    # nama kunci lama dipertahankan
(OUT / "params.json").write_text(json.dumps(params, indent=2))

# ---------- Siswa ----------
s2 = pd.read_excel(SRC, sheet_name="Sheet2", header=None, skiprows=6, usecols="A:I")
s2.columns = ["no_awal", "nama", "nisn", "nis", "kelas", "jumlah", "rata_rata", "bobot", "nilai_komposit"]
s2 = s2.dropna(subset=["nama"]).copy()
s2["nisn"] = s2["nisn"].astype("Int64").astype(str)
s2, info = tetapkan_no(s2, OUT / "id_siswa.csv")
s2["peringkat"] = s2["rata_rata"].rank(method="min", ascending=False).astype(int)

# nilai pendukung yang sudah terisi di Pemetaan_Massal (jika ada)
pm = pd.read_excel(SRC, sheet_name="Pemetaan_Massal", header=5, usecols="B:Z", nrows=140).dropna(subset=["Nama Siswa"])
pre = pm[["Nama Siswa", "Nilai Pendukung P1", "Nilai Pendukung P2"]].rename(
    columns={"Nama Siswa": "nama", "Nilai Pendukung P1": "pend_p1", "Nilai Pendukung P2": "pend_p2"}
).drop_duplicates("nama")
s2 = s2.merge(pre, on="nama", how="left")
kolom = ["no", "peringkat", "nama", "kelas", "jumlah", "rata_rata", "bobot", "nilai_komposit", "pend_p1", "pend_p2"]
s2.sort_values(["peringkat", "no"])[kolom].to_csv(OUT / "siswa.csv", index=False)   # NISN/NIS sengaja tidak disimpan
print(f"Siswa: {len(s2)} | siswa baru diberi nomor: {info['baru'] or '-'} | nomor lama yang tidak ada lagi: {info['tidak_ada_lagi']}")

# ---------- Referensi prodi ----------
rp = pd.read_excel(SRC, sheet_name="Referensi_Prodi", header=3, usecols="B:O")
rp = rp.rename(columns={
    "Nama PTN": "ptn", "Program Studi (Lengkap)": "prodi", "Jenjang": "jenjang",
    "DT 2025": "dt_2025", "Peminat 2025": "peminat_2025", "DT 2026": "dt_2026",
    "Keketatan Prodi": "keketatan_prodi", "Alumni Jurusan": "alumni_jur",
    "Mapel Pendukung 1": "mapel1", "Mapel Pendukung 2": "mapel2", "Mapel Pendukung 3": "mapel3",
    "Jenis Mapel Pendukung": "jenis_mapel"})
rp = rp[["ptn", "prodi", "jenjang", "dt_2025", "peminat_2025", "dt_2026", "keketatan_prodi",
         "alumni_jur", "mapel1", "mapel2", "mapel3", "jenis_mapel"]]
rp["alumni_jur"] = rp["alumni_jur"].fillna(0)
rp.to_csv(OUT / "prodi.csv", index=False)

# ---------- Referensi PTN ----------
pt = pd.read_excel(SRC, sheet_name="Referensi_PTN", header=3, usecols="C:K")
pt.columns = ["ptn", "jumlah_prodi", "dt_2025", "peminat_2025", "dt_2026",
              "keketatan_kampus", "alumni_ptn", "provinsi", "kota"]
pt.dropna(subset=["ptn"]).to_csv(OUT / "ptn.csv", index=False)

# ---------- Data historis (kalibrasi model) ----------
h = pd.read_excel(SRC, sheet_name="Data_Historis_198", header=3, usecols="B:O")
h.columns = ["no", "nilai", "ptn", "prodi", "pendukung", "alumni_ptn", "alumni_jur",
             "keketatan_prodi", "keketatan_kampus", "pilihan_ke", "aktual", "logit_excel",
             "peluang_excel", "zona_excel"]
h.dropna(subset=["nilai"]).to_csv(OUT / "historis.csv", index=False)

print("Selesai. File di folder data/:", ", ".join(sorted(p.name for p in OUT.iterdir())))

# ---------- Batas maksimal pendaftar per PTN (dihitung ulang dari data terbaru) ----------
try:
    sys.path.insert(0, str(AKAR))
    import batas_ptn
    import model as _m
    _p, *_ = batas_ptn.hitung(_m.Ref())
    _p[["ptn", "batas", "tingkat", "alasan", "alumni_ptn", "dipilih_2026", "lolos_2026", "siswa_realistis",
        "provinsi"]].to_csv(OUT / "batas_ptn.csv", index=False)
    print(f"Batas PTN dihitung ulang: {len(_p)} PTN, batas terbesar {int(_p.batas.max())}.")
except Exception as e:  # noqa: BLE001
    print("PERINGATAN: batas PTN tidak dihitung ulang:", e)
