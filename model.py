"""Logika model regresi logistik SNBP (identik dengan formula di Excel)."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"

FAKTOR = [  # (kunci parameter, label)
    ("nilai", "Nilai komposit"),
    ("pendukung", "Mapel pendukung"),
    ("alumni_ptn", "Alumni di PTN"),
    ("alumni_jur", "Alumni di jurusan"),
    ("keketatan_prodi", "Keketatan prodi (%)"),
    ("keketatan_kampus", "Keketatan kampus (%)"),
    ("pilihan_2", "Penalti Pilihan 2"),
]


def load_params() -> dict:
    return json.loads((DATA / "params.json").read_text())


def _x(ket_prodi, ket_kampus, cap=False):
    """Keketatan efektif (dalam persen). Prodi baru (0) memakai keketatan kampus."""
    kp = np.asarray(ket_prodi, dtype=float)
    kk = np.asarray(ket_kampus, dtype=float)
    if cap:
        kp = np.minimum(kp, 1.0)
    return np.where(kp == 0, kk, kp) * 100.0, kk * 100.0


def logit(p, nilai, pend, alm_ptn, alm_jur, ket_prodi, ket_kampus, pilihan2, cap=False):
    kp, kk = _x(ket_prodi, ket_kampus, cap)
    return (p["intercept"] + p["nilai"] * np.asarray(nilai, dtype=float)
            + p["pendukung"] * np.asarray(pend, dtype=float)
            + p["alumni_ptn"] * np.asarray(alm_ptn, dtype=float)
            + p["alumni_jur"] * np.asarray(alm_jur, dtype=float)
            + p["keketatan_prodi"] * kp + p["keketatan_kampus"] * kk
            + p["pilihan_2"] * np.asarray(pilihan2, dtype=float))


def prob(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -700, 700)))


def status(pr, cut_aman, cut_kompetitif):
    pr = np.asarray(pr, dtype=float)
    return np.where(pr >= cut_aman, "AMAN", np.where(pr >= cut_kompetitif, "KOMPETITIF", "BERISIKO"))


def kontribusi(p, nilai, pend, alm_ptn, alm_jur, ket_prodi, ket_kampus, pilihan2, cap=False):
    """Rincian kontribusi tiap faktor terhadap logit (untuk penjelasan ke siswa)."""
    kp, kk = _x(ket_prodi, ket_kampus, cap)
    nilai_x = {"nilai": nilai, "pendukung": pend, "alumni_ptn": alm_ptn, "alumni_jur": alm_jur,
               "keketatan_prodi": float(kp), "keketatan_kampus": float(kk), "pilihan_2": pilihan2}
    rows = [{"Faktor": "Intercept", "Nilai": np.nan, "Beta": p["intercept"], "Kontribusi": p["intercept"]}]
    for k, label in FAKTOR:
        rows.append({"Faktor": label, "Nilai": nilai_x[k], "Beta": p[k], "Kontribusi": p[k] * nilai_x[k]})
    return pd.DataFrame(rows)


def strategi(st1, st2):
    """Saran kombinasi Pilihan 1 + Pilihan 2 (sama dengan kolom 'Saran Strategi Kombinasi')."""
    if not st1:
        return ""
    if not st2:
        return "Isi Pilihan 2 sebagai pengaman"
    if "AMAN" in (st1, st2):
        return "Kombinasi Ideal (Ada Opsi Aman)"
    if "KOMPETITIF" in (st1, st2):
        return "Perlu Pengaman di Pilihan 2"
    return "Evaluasi Ulang Kedua Pilihan"


def gabungan(p1, p2=None):
    """Peluang minimal 1 lolos."""
    if p2 is None or pd.isna(p2):
        return p1
    return 1 - (1 - p1) * (1 - p2)


def auc(y, score):
    """ROC-AUC (rank-based, tanpa sklearn)."""
    y = np.asarray(y).astype(int)
    s = pd.Series(score).rank().to_numpy()
    n1, n0 = y.sum(), (1 - y).sum()
    return (s[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


# ---------- Data ----------
def load_siswa():
    return pd.read_csv(DATA / "siswa.csv", dtype={"nisn": str, "nis": str})


def load_prodi(ptn: pd.DataFrame) -> pd.DataFrame:
    d = pd.read_csv(DATA / "prodi.csv")
    d = d.merge(ptn[["ptn", "keketatan_kampus", "alumni_ptn", "provinsi", "kota"]], on="ptn", how="left")
    d[["keketatan_kampus", "alumni_ptn"]] = d[["keketatan_kampus", "alumni_ptn"]].fillna(0)
    d["mapel_list"] = d[["mapel1", "mapel2", "mapel3"]].apply(lambda r: [m for m in r if isinstance(m, str) and m.strip() not in ("", "-")], axis=1)
    return d


def load_ptn():
    return pd.read_csv(DATA / "ptn.csv")


def load_historis():
    return pd.read_csv(DATA / "historis.csv")


def prodi_batch(p, df, nilai, pend, pilihan2, cap=False):
    """Hitung peluang untuk banyak prodi sekaligus (dipakai tab Rekomendasi)."""
    z = logit(p, nilai, pend, df["alumni_ptn"], df["alumni_jur"], df["keketatan_prodi"],
              df["keketatan_kampus"], pilihan2, cap)
    return prob(z)


# =====================================================================
#  Lapisan "aplikasi" — dipakai oleh app.py (semua tanpa dependensi Streamlit)
# =====================================================================
class Ref:
    """Seluruh data referensi, dimuat sekali."""

    def __init__(self):
        self.params = load_params()
        self.ptn = load_ptn()
        self.prodi = load_prodi(self.ptn)
        self.siswa = load_siswa()
        self.hist = load_historis()
        self.ptn_list = sorted(self.ptn["ptn"].unique())
        self.idx = {(r["ptn"], r["prodi"]): r for r in self.prodi.to_dict("records")}
        self.canon = {(k[0].upper(), k[1].upper()): k for k in self.idx}
        self.prodi_opsi = {k: sorted(g["prodi"]) for k, g in self.prodi.groupby("ptn")}
        self.mapel_semua = sorted({x for L in self.prodi["mapel_list"] for x in L})


def evaluasi(ref, sis, ptn, prodi, nilai, pilihan2, cut_a, cut_k):
    """Hitung peluang satu pilihan. Mengembalikan dict atau None bila input belum lengkap."""
    if not ptn or not prodi or nilai is None or pd.isna(nilai):
        return None
    row = ref.idx.get((ptn, prodi))
    if row is None:
        return None
    args = (ref.params, sis["nilai_komposit"], nilai, row["alumni_ptn"], row["alumni_jur"],
            row["keketatan_prodi"], row["keketatan_kampus"], pilihan2)
    z = float(logit(*args))
    pr = float(prob(z))
    return {"row": row, "nilai": float(nilai), "z": z, "p": pr, "status": str(status(pr, cut_a, cut_k)),
            "args": args}


def rekomendasi(ref, sis, acuan, nilai, cut_a, cut_k, sembunyikan_anomali=True):
    """Semua prodi yang memiliki >= 1 mapel pendukung sama dengan `acuan`, lengkap dengan peluang P1 & P2."""
    acuan = set(acuan)
    d = ref.prodi
    mask = d["mapel_list"].apply(lambda L: bool(acuan.intersection(L)))
    d = d[mask].copy()
    n_anomali = int((d["keketatan_prodi"] > 1).sum())
    if sembunyikan_anomali:
        d = d[d["keketatan_prodi"] <= 1]
    d["p1"] = prodi_batch(ref.params, d, sis["nilai_komposit"], nilai, 0)
    d["p2"] = prodi_batch(ref.params, d, sis["nilai_komposit"], nilai, 1)
    d["status1"] = status(d["p1"], cut_a, cut_k)
    d["status2"] = status(d["p2"], cut_a, cut_k)
    return d, n_anomali


PIL_COLS = ["no", "ptn1", "prodi1", "nilai1", "ptn2", "prodi2", "nilai2"]


def tabel_massal(ref, pilihan, cut_a, cut_k):
    rows = []
    for _, s in ref.siswa.iterrows():
        rec = pilihan.get(int(s["no"])) or {}
        r1 = evaluasi(ref, s, rec.get("ptn1"), rec.get("prodi1"), rec.get("nilai1"), 0, cut_a, cut_k)
        r2 = evaluasi(ref, s, rec.get("ptn2"), rec.get("prodi2"), rec.get("nilai2"), 1, cut_a, cut_k)
        p1 = r1["p"] if r1 else np.nan
        p2 = r2["p"] if r2 else np.nan
        rows.append({
            "No": int(s["no"]), "Nama Siswa": s["nama"], "Kelas": s["kelas"],
            "Nilai Komposit": s["nilai_komposit"],
            "PTN Pilihan 1": rec.get("ptn1"), "Prodi Pilihan 1": rec.get("prodi1"),
            "Nilai Pendukung P1": r1["nilai"] if r1 else np.nan,
            "Peluang P1": p1, "Status P1": r1["status"] if r1 else "",
            "PTN Pilihan 2": rec.get("ptn2"), "Prodi Pilihan 2": rec.get("prodi2"),
            "Nilai Pendukung P2": r2["nilai"] if r2 else np.nan,
            "Peluang P2": p2, "Status P2": r2["status"] if r2 else "",
            "Peluang Min. 1 Lolos": gabungan(p1, p2) if r1 else np.nan,
            "Saran Strategi": strategi(r1["status"] if r1 else "", r2["status"] if r2 else ""),
        })
    return pd.DataFrame(rows)


TEMPLATE_COLS = ["Nama Siswa", "PTN Pilihan 1", "Prodi Pilihan 1", "Nilai Pendukung P1",
                 "PTN Pilihan 2", "Prodi Pilihan 2", "Nilai Pendukung P2"]


def impor_pilihan(ref, df):
    """Validasi & ubah tabel impor menjadi dict pilihan {no: {...}}. Mengembalikan (hasil, daftar_error)."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    hilang = [c for c in TEMPLATE_COLS if c not in df.columns]
    if hilang:
        return {}, [f"Kolom tidak ditemukan: {', '.join(hilang)}"]
    by_name = {n.strip().upper(): (int(no), r) for no, n, r in zip(ref.siswa["no"], ref.siswa["nama"], ref.siswa["rata_rata"])}
    hasil, errs = {}, []
    for i, r in df.iterrows():
        nama = str(r["Nama Siswa"]).strip().upper()
        if nama not in by_name:
            errs.append(f"Baris {i + 2}: siswa '{r['Nama Siswa']}' tidak ada di daftar")
            continue
        no, rata = by_name[nama]
        rec = {}
        for k in ("1", "2"):
            p_, d_, n_ = r[f"PTN Pilihan {k}"], r[f"Prodi Pilihan {k}"], r[f"Nilai Pendukung P{k}"]
            if pd.isna(p_) or pd.isna(d_) or str(p_).strip() == "":
                rec.update({f"ptn{k}": None, f"prodi{k}": None, f"nilai{k}": None})
                continue
            kunci = ref.canon.get((str(p_).strip().upper(), str(d_).strip().upper()))
            if kunci is None:
                errs.append(f"Baris {i + 2} ({r['Nama Siswa']}): kombinasi PTN/prodi Pilihan {k} tidak ditemukan di database")
                rec.update({f"ptn{k}": None, f"prodi{k}": None, f"nilai{k}": None})
                continue
            nilai = float(n_) if pd.notna(n_) else float(rata)
            rec.update({f"ptn{k}": kunci[0], f"prodi{k}": kunci[1], f"nilai{k}": nilai})
        if rec.get("ptn1") or rec.get("ptn2"):
            hasil[no] = rec
    return hasil, errs


def saring_rek(d, sumber, status_filter, jenjang=(), provinsi=(), ptn=(), cari=""):
    """Terapkan filter tab Rekomendasi pada hasil `rekomendasi()` lalu urutkan dari peluang tertinggi."""
    kol_st = "status1" if sumber == "Pilihan 1" else "status2"
    kol_p = "p1" if sumber == "Pilihan 1" else "p2"
    if status_filter == "AMAN saja":
        d = d[d[kol_st] == "AMAN"]
    elif status_filter == "AMAN + KOMPETITIF":
        d = d[d[kol_st].isin(["AMAN", "KOMPETITIF"])]
    if jenjang:
        d = d[d["jenjang"].isin(list(jenjang))]
    if provinsi:
        d = d[d["provinsi"].isin(list(provinsi))]
    if ptn:
        d = d[d["ptn"].isin(list(ptn))]
    if cari:
        d = d[d["prodi"].str.contains(cari, case=False, na=False, regex=False)]
    return d.sort_values(kol_p, ascending=False)
