# Swing Saham — Invezgo API

Aplikasi Streamlit untuk riset swing trading saham IDX menggunakan [Invezgo API](https://docs.invezgo.com/api/).

**Bukan rekomendasi/ajakan jual-beli — murni alat bantu riset & edukasi.**

## Fitur

- **Screener** — top gainers/losers, akumulasi/distribusi asing & ritel harian, plus screener formula custom (`POST /screener/screen`).
- **Analisa Saham** — candlestick + deteksi support/resistance otomatis (fractal swing) + trading plan (entry/stop/target berbasis ATR) + kalkulator lot sizing.
- **Bandarmologi** — broker summary, inventory chart (akumulasi broker dari waktu ke waktu), sankey aliran dana antar broker, dan broker stalker.
- **Watchlist & Alert** — kelola grup watchlist pribadi dan alert formula real-time lewat akun Invezgo Anda.
- **Strategy Screener** — engine screening berbasis *condition tree* (JSON, bukan kode) sesuai spesifikasi internal (`skema-query-screening-engine.md` & `strategi-teknikal-bandarmologi-swing.md`): 11 strategi siap pakai (breakout+broker, stealth accumulation, oversold reversal, trend pullback, broker rotation warning, 5 strategi swing klasik, dan ranking komposit multi-saham), dievaluasi terhadap universe saham pilihan Anda.

## Peran Admin & User

Aplikasi punya dua peran, tanpa sistem akun per-pengguna:

- **Admin** — login dengan satu password bersama (`ADMIN_PASSWORD` di secrets) lewat panel "🔐 Admin Login" di sidebar. Setelah login, panel di halaman Home muncul untuk mengisi/mengganti/menghapus Invezgo API Key. Key ini **tidak pernah ditulis ke kode/repo** — tersimpan di berkas lokal terenkripsi (`.data/api_key.enc`, di-gitignore) yang dipakai bersama oleh semua pengguna.
- **User biasa** — langsung pakai semua fitur aplikasi tanpa login, dan **tidak pernah melihat atau bisa mengisi API Key**. Kalau Admin belum mengisi key, mereka cuma melihat pesan "hubungi admin".

Dapatkan API key Invezgo di [invezgo.com/id/setting/api](https://invezgo.com/id/setting/api) (butuh paket langganan aktif).

### Secrets yang perlu diisi (lihat `.streamlit/secrets.toml.example`)

| Secret | Wajib? | Fungsi |
|---|---|---|
| `ADMIN_PASSWORD` | Wajib untuk panel Admin | Password login admin. Tanpa ini, panel Admin tidak bisa diakses sama sekali. |
| `APP_SECRET_KEY` | Disarankan | Kunci enkripsi untuk API Key yang disimpan Admin. Tanpa ini, key tetap tersimpan tapi hanya di-obfuscate (base64), bukan dienkripsi. |
| `INVEZGO_API_KEY` | Opsional (cadangan) | Dipakai kalau berkas key lokal belum/tidak ada — lihat catatan persistensi di bawah. |

### Persistensi API Key

Key yang diisi Admin lewat panel tersimpan di berkas lokal dan bertahan lintas sesi & lintas pengguna selama container aplikasi tidak di-*redeploy*. Di Streamlit Community Cloud, *redeploy* (push commit baru) melakukan clone ulang repo sehingga berkas lokal ini hilang — supaya key tetap "hidup selamanya" walau begitu, isi juga `INVEZGO_API_KEY` di secrets sebagai cadangan permanen (secrets Streamlit Cloud tidak ikut hilang saat redeploy). Urutan prioritas: key dari panel Admin dipakai duluan kalau ada, baru jatuh ke `INVEZGO_API_KEY`.

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy ke Streamlit Community Cloud

1. Push repo ini ke GitHub (repo boleh publik — tidak ada key yang ter-commit).
2. Buka [share.streamlit.io](https://share.streamlit.io), hubungkan repo, pilih `app.py` sebagai entry point.
3. Isi `ADMIN_PASSWORD` (wajib), `APP_SECRET_KEY` (disarankan), dan `INVEZGO_API_KEY` (opsional, cadangan) di Settings → Secrets.
4. Buka app, login sebagai Admin di sidebar, lalu isi API Key lewat panel di halaman Home. Selesai — pengguna lain langsung bisa pakai aplikasi tanpa setup apapun.

## Struktur Project

```
app.py                      # Home: panel Admin (login + kelola API key) + ringkasan pasar
pages/
  1_Screener.py
  2_Analisa_Saham.py
  3_Bandarmologi.py
  4_Watchlist_Alert.py
  5_Strategy_Screener.py
invezgo/client.py           # Wrapper tipis untuk Invezgo REST API
utils/
  auth.py                   # Login/logout admin (session-based) + widget sidebar
  key_store.py              # Penyimpanan API key persisten terenkripsi (dipakai lintas sesi/user)
  indicators.py             # ATR, fractal S/R, trading plan, lot sizing (dipakai Analisa Saham)
  formatting.py             # Format Rupiah/angka/tanggal
  state.py                  # Resolusi API key (key_store -> secrets) & client
screening/                  # Engine Strategy Screener
  technicals.py             # Field Registry teknikal (SMA/EMA/MACD/RSI/ATR/ADX/Donchian/OBV/VWAP, dll)
  broker.py                 # Field Registry bandarmologi (broker_net_value, inventory, konsentrasi top-5)
  candlestick.py            # Deteksi pola candle (hammer, bullish engulfing, dragonfly doji, inside-day break)
  condition_tree.py         # Evaluator and/or/not + agregator (sum/avg/streak/sign_change/slope/pct_change)
  engine.py                 # Orkestrasi fetch->enrich->evaluate, screening boolean & ranking komposit
  strategies/*.json         # 11 definisi strategi (data, bukan kode — lihat prinsip di §9 spesifikasi)
tests/
  test_engine_offline.py    # Smoke test field registry + semua strategi pakai data sintetis (tanpa API call)
  test_engine_run.py        # Smoke test run_screening/run_ranking end-to-end pakai fake client
```

Jalankan smoke test (tanpa API key, tanpa panggilan jaringan):

```bash
python -m tests.test_engine_offline
python -m tests.test_engine_run
```

## Batasan

- Invezgo membatasi data historis maksimal 2 tahun ke belakang untuk seluruh endpoint (paket non-Enterprise).
- Trading plan yang dihasilkan bersifat rule-based (struktur harga historis), bukan prediksi — selalu lakukan analisa dan manajemen risiko sendiri.
- **Strategy Screener** memanggil 2 endpoint per saham (chart + inventory), jadi universe besar akan lambat — defaultnya dibatasi 60 saham per run. Beberapa field di spesifikasi butuh pendekatan karena keterbatasan bentuk data Invezgo (didokumentasikan sebagai komentar di kode):
  - `value` (nilai transaksi) didekati dengan `close × volume` (bukan angka transaksi eksak).
  - `broker_concentration_top5` didekati dari broker-broker signifikan yang dikembalikan endpoint inventory (bukan dari total volume pasar sesungguhnya).
  - `anchored_vwap` di-anchor dari awal rentang data yang diambil, bukan dari tanggal event tertentu.
  - Field fundamental (`per`, `pbv`, `roe`, dst) dan `foreign_net_value`/`news`/`disclosure` belum diimplementasikan karena tidak dipakai strategi manapun di v1 — mereferensikannya di strategi baru akan menghasilkan error validasi yang jelas (sesuai §1 spesifikasi), bukan disilent-skip.
