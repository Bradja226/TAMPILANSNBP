"""Hitung batas maksimal pendaftar per PTN (jumlah siswa yang boleh memilih PTN itu, sebagai Pilihan 1 maupun 2).
Dasar: jejak alumni, lokasi, keketatan kampus, peluang model, dan hasil pemetaan 2026."""
import numpy as np
import pandas as pd

import model as m

ZONA1 = {"Jawa Barat", "Banten", "Jakarta Raya"}
ZONA2 = {"Jawa Tengah", "Yogyakarta", "Jawa Timur"}
AMBANG_REALISTIS = 0.1122  # tetap (terpisah dari ambang zona) supaya batas PTN stabil
FAKTOR_REALISTIS = 1.3     # batas tidak boleh melebihi 1,3 x jumlah siswa yang punya peluang realistis


def dasar_alumni(a):
    if a >= 30: return "A. Andalan utama", 54
    if a >= 10: return "B. Andalan", 25
    if a >= 5:  return "C. Penyangga kuat", 15
    if a >= 2:  return "D. Penyangga", 10
    if a >= 1:  return "E. Rintisan", 6
    return None, None


def hitung(R):
    P = R.params; ck = AMBANG_REALISTIS
    d = R.prodi[R.prodi.keketatan_prodi <= 1].reset_index(drop=True)       # buang prodi 'tidak wajar' (keketatan > 100%)
    ptns = sorted(R.ptn.ptn.unique()); pos = {p: i for i, p in enumerate(ptns)}; idx = d.ptn.map(pos).values
    # siswa 2027 yang punya >=1 prodi realistis (peluang >= batas KOMPETITIF) di tiap PTN. Nilai mapel = rata-rata rapor (proksi).
    ada = np.zeros((len(R.siswa), len(ptns)), bool)
    for a, s in enumerate(R.siswa.itertuples()):
        pr = m.prodi_batch(P, d, s.nilai_komposit, s.rata_rata, 0)
        ada[a] = np.bincount(idx, weights=(pr >= ck).astype(float), minlength=len(ptns)) > 0
    h = R.hist.copy()
    h["p"] = m.prob(m.logit(P, h.nilai, h.pendukung, h.alumni_ptn, h.alumni_jur, h.keketatan_prodi, h.keketatan_kampus, (h.pilihan_ke == 2).astype(int)))
    h["y"] = (h.aktual == "YA").astype(int); h["real"] = (h.p >= ck).astype(int)
    g = h.groupby("ptn").agg(dipilih_2026=("y", "size"), lolos_2026=("y", "sum"), realistis_2026=("real", "sum"))
    p = R.ptn.merge(g, left_on="ptn", right_index=True, how="left").fillna({"dipilih_2026": 0, "lolos_2026": 0, "realistis_2026": 0})
    p["siswa_realistis"] = p.ptn.map(dict(zip(ptns, ada.sum(0)))).fillna(0).astype(int)
    p["zona"] = np.where(p.provinsi.isin(ZONA1), "1 (Jabar-Banten-Jakarta)", np.where(p.provinsi.isin(ZONA2), "2 (Jawa lain)", "3 (Luar Jawa)"))
    out = []
    for r in p.itertuples():
        tier, cap = dasar_alumni(r.alumni_ptn); alasan = []
        if tier:
            alasan.append(f"{int(r.alumni_ptn)} alumni sekolah diterima di sini")
        else:
            tier, cap = (("F. Terjangkau (dekat)", 6) if r.zona[0] == "1" else ("G. Terjangkau (Jawa)", 4) if r.zona[0] == "2" else ("H. Jauh", 2))
            alasan.append({"F": "belum ada alumni, lokasi dekat: batas kecil untuk uji coba", "G": "belum ada alumni, di Jawa: batas kecil",
                           "H": "belum ada alumni dan di luar Jawa: batas minimal"}[tier[0]])
        if r.keketatan_kampus < 0.10:
            cap = max(2, int(np.ceil(cap * 0.6))); alasan.append(f"sangat ketat (DT/peminat {r.keketatan_kampus:.1%}): batas dikurangi 40%")
        real = max(r.siswa_realistis, r.realistis_2026)
        lim = int(np.ceil(FAKTOR_REALISTIS * real))
        if lim < cap:
            cap = max(2, lim); alasan.append(f"dibatasi jumlah siswa realistis ({int(real)} siswa × 1,3)")
        if r.dipilih_2026 > 0 and cap < 4:
            cap = 4; alasan.append("dipilih siswa tahun lalu: minimal 4")
        out.append((tier, int(cap), "; ".join(alasan)))
    p[["tingkat", "batas", "alasan"]] = pd.DataFrame(out, index=p.index)
    return p.sort_values(["tingkat", "batas", "alumni_ptn"], ascending=[True, False, False]).reset_index(drop=True), ada, ptns, h
