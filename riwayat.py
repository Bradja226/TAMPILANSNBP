"""Pembantu tampilan riwayat perubahan pilihan (tanpa dependensi Streamlit, mudah diuji)."""
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
IKON = {"memilih": "➕", "mengganti": "🔁", "menghapus": "➖"}
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def sekarang():
    return datetime.now(WIB).replace(tzinfo=None)


def parse(w):
    return datetime.strptime(w, "%Y-%m-%d %H:%M:%S")


def lalu(w, now=None):
    """'baru saja', '5 menit lalu', '3 jam lalu', '2 hari lalu'."""
    d = ((now or sekarang()) - parse(w)).total_seconds()
    if d < 60:
        return "baru saja"
    if d < 3600:
        return f"{int(d // 60)} menit lalu"
    if d < 86400:
        return f"{int(d // 3600)} jam lalu"
    return f"{int(d // 86400)} hari lalu"


def waktu_pendek(w):
    t = parse(w)
    return f"{t.day} {BULAN[t.month - 1]} {t:%H:%M}"


def baru(w, menit=30, now=None):
    return 0 <= ((now or sekarang()) - parse(w)).total_seconds() < menit * 60


def kalimat(r, nama, tebal=True):
    """Kalimat perubahan, mis. 'Ani memilih Kedokteran di Universitas B sebagai Pilihan 1'."""
    b = (lambda s: f"**{s}**") if tebal else (lambda s: s)
    k = f"Pilihan {r['pilihan']}"
    if r["aksi"] == "memilih":
        return f"{b(nama)} memilih {b(r['prodi_baru'])} di {b(r['ptn_baru'])} sebagai {k}"
    if r["aksi"] == "mengganti":
        return (f"{b(nama)} mengganti {k} dari {r['prodi_lama']} ({r['ptn_lama']}) "
                f"menjadi {b(r['prodi_baru'])} di {b(r['ptn_baru'])}")
    return f"{b(nama)} menghapus {k} ({r['prodi_lama']} di {r['ptn_lama']})"
