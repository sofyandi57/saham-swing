# Swing Saham — Invezgo API

Aplikasi Streamlit untuk riset swing trading saham IDX menggunakan [Invezgo API](https://docs.invezgo.com/api/).

**Bukan rekomendasi/ajakan jual-beli — murni alat bantu riset & edukasi.**

## Fitur

- **Screener** — top gainers/losers, akumulasi/distribusi asing & ritel harian, plus screener formula custom (`POST /screener/screen`).
- **Analisa Saham** — candlestick + deteksi support/resistance otomatis (fractal swing) + trading plan (entry/stop/target berbasis ATR) + kalkulator lot sizing.
- **Bandarmologi** — broker summary, inventory chart (akumulasi broker dari waktu ke waktu), sankey aliran dana antar broker, dan broker stalker.
- **Watchlist & Alert** — kelola grup watchlist pribadi dan alert formula real-time lewat akun Invezgo Anda.

## API Key

Aplikasi ini **tidak menyimpan API key di kode atau repo**. Saat dijalankan, masukkan API Key Invezgo Anda di sidebar (field password) — key hanya hidup di sesi browser Anda.

Dapatkan API key di [invezgo.com/id/setting/api](https://invezgo.com/id/setting/api) (butuh paket langganan aktif).

Untuk deployment pribadi, Anda juga bisa mengisi `INVEZGO_API_KEY` di Streamlit secrets (lihat `.streamlit/secrets.toml.example`) supaya key terisi otomatis — file ini di-gitignore dan tidak pernah masuk ke repo publik.

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy ke Streamlit Community Cloud

1. Push repo ini ke GitHub (repo boleh publik — tidak ada key yang ter-commit).
2. Buka [share.streamlit.io](https://share.streamlit.io), hubungkan repo, pilih `app.py` sebagai entry point.
3. (Opsional) Isi secret `INVEZGO_API_KEY` di Settings → Secrets jika ingin key terisi otomatis. Jika tidak, setiap pengguna cukup mengisi API key mereka sendiri di sidebar saat membuka app.

## Struktur Project

```
app.py                      # Home: input API key + ringkasan pasar
pages/
  1_Screener.py
  2_Analisa_Saham.py
  3_Bandarmologi.py
  4_Watchlist_Alert.py
invezgo/client.py           # Wrapper tipis untuk Invezgo REST API
utils/
  indicators.py             # ATR, fractal S/R, trading plan, lot sizing
  formatting.py             # Format Rupiah/angka/tanggal
  state.py                  # Helper session_state untuk API key & client
```

## Batasan

- Invezgo membatasi data historis maksimal 2 tahun ke belakang untuk seluruh endpoint (paket non-Enterprise).
- Trading plan yang dihasilkan bersifat rule-based (struktur harga historis), bukan prediksi — selalu lakukan analisa dan manajemen risiko sendiri.
