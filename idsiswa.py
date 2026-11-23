"""Nomor siswa yang TETAP (tidak ikut berubah saat peringkat bergeser).

Setiap siswa dikenali dari NISN (disimpan hanya sebagai kode acak/hash di data/id_siswa.csv).
Siswa lama selalu mempertahankan nomornya; siswa baru mendapat nomor berikutnya; nomor tidak pernah dipakai ulang."""
import hashlib
from pathlib import Path

import pandas as pd

GARAM = "snbp-ciampea-2027"


def kunci(nisn=None, nama=None):
    n = "" if nisn is None else str(nisn).strip()
    basis = n if n not in ("", "nan", "<NA>", "None") else f"nama:{str(nama).strip().upper()}"
    return hashlib.sha256(f"{GARAM}|{basis}".encode()).hexdigest()[:16]


def tetapkan_no(df, peta_csv):
    """df wajib punya kolom: nama, nisn, no_awal. Mengembalikan (df + kolom 'no', info)."""
    peta_csv = Path(peta_csv)
    df = df.copy()
    df["_k"] = [kunci(a, b) for a, b in zip(df["nisn"], df["nama"])]
    if df["_k"].duplicated().any():
        dup = df.loc[df["_k"].duplicated(keep=False), "nama"].tolist()
        raise ValueError(f"Ada NISN/nama kembar di Excel: {dup[:5]}. Periksa dulu datanya.")
    if peta_csv.exists():
        lama = pd.read_csv(peta_csv, dtype={"kunci": str})
        peta = {k: int(v) for k, v in zip(lama["kunci"], lama["no"])}
    else:   # pertama kali: pakai nomor di Excel sebagai nomor awal
        awal = df["no_awal"]
        if awal.notna().all() and awal.is_unique:
            peta = dict(zip(df["_k"], awal.astype(int)))
        else:
            peta = {k: i + 1 for i, k in enumerate(df["_k"])}
    baru, nxt = [], max(peta.values(), default=0) + 1
    for k in df["_k"]:
        if k not in peta:
            peta[k] = nxt
            baru.append(nxt)
            nxt += 1
    df["no"] = df["_k"].map(peta).astype(int)
    pd.DataFrame(sorted(peta.items(), key=lambda kv: kv[1]), columns=["kunci", "no"]).to_csv(peta_csv, index=False)
    return df.drop(columns="_k"), {"baru": baru, "tidak_ada_lagi": len(set(peta.values()) - set(df["no"]))}
