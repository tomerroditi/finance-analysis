---
paths:
  - "scraper/providers/banks/onezero.py"
  - "scraper/providers/banks/onezero_mtls/**/*"
---
# OneZero mutual-TLS (Cloudflare client certificate)

Read this before touching the OneZero scraper's transport, the vendored cert
files, or when OneZero scraping suddenly starts returning a Cloudflare 403
"Attention Required" block.

## What's going on

OneZero has no web app — the scraper (`scraper/providers/banks/onezero.py`)
replays the mobile app's API calls. As of **2026-08**, OneZero put its API
hosts behind **Cloudflare mTLS** (mutual TLS / API Shield client
certificates):

- `identity.tfd-bank.com` (OTP + login) and `mobile.tfd-bank.com`
  (GraphQL data) now **require a client certificate** issued by Cloudflare's
  managed CA.
- A request without it is rejected by Cloudflare with **HTTP 403 + an
  "Attention Required" HTML block page**, *before* it reaches OneZero — so it
  fails at the very first pre-login call (`POST /v1/devices/token`), which is
  the symptom users report ("could not obtain an OTP token … 403").
- The marketing site `www.onezerobank.com` has no mTLS and still returns 200,
  which is how you can tell this apart from an IP ban or a TLS-fingerprint
  block. Neither residential proxies, `show_browser`, delays, nor UA/JA3
  spoofing help — the gate is the client certificate, nothing else.

## Why we can vendor it (and why it's safe to commit)

The certificate is **bundled in the app's APK and shared across every
install** — it is not provisioned per-device into a hardware keystore. It
authenticates "a OneZero app," not a user or an account. Verified on the
4.4.2 (build 530) APK:

- The *only* two classes that touch it (`CloudFlareUseCase` / `hx1`,
  `TrustCertificateUseCase` / `opb`) read the **static `R.raw.mtls_cert` /
  `mtls_key`** resources. There is no per-user provisioning anywhere — no
  Android Keystore keypair, no cert downloaded at enrollment.
- The cert's subject is the generic org `C=IL, O=One Zero, CN=OneZero` — no
  personal CN, email, ID, phone, or SAN. Issuer is **Cloudflare Managed CA**.
- It's presented *before* login, so it cannot be identifying you.

So it is public-by-construction (anyone can download the app and extract it,
no account needed) and leaking it cannot expose any account. We therefore
vendor the two PEM files directly in the repo at
`scraper/providers/banks/onezero_mtls/`. The only real downside of the cert
being public is that OneZero might notice and rotate it sooner — in which case
you re-extract (below). Validity of the current cert: **2026-08-05 →
2027-08-05**; re-extract before expiry or after any OneZero app update that
ships a new cert.

## How it's wired in the code

- `scraper/providers/banks/onezero_mtls/mtls_cert.pem` + `mtls_key.key` —
  the vendored, extracted PEM files (committed).
- `scraper/providers/banks/onezero.py` — `MTLS_CERT_PATH` / `MTLS_KEY_PATH`
  point at those files; `OneZeroScraper.initialize()` builds
  `httpx.AsyncClient(cert=(cert, key))` so every request presents the client
  certificate. If the files are missing it raises `OneZeroMtlsError` with an
  actionable message (pointing here) instead of failing later with the opaque
  Cloudflare 403.

No keyring, no adapter injection, no user-dir stash — the cert is a normal
bundled resource, loaded straight from disk.

## Runbook — re-extract the certificate (after a rotation / expiry)

Prerequisites: an Android device (or emulator) with the OneZero app
installed, `adb`, plus `unzip`, `openssl`, `curl`. `jadx` optional (only for
re-analysing the app if the fix below doesn't work).

1. **Pull the APK** from a device with the app installed:

   ```bash
   adb shell pm path il.co.firstdigitalbank | sed 's/package://' \
     | while read p; do adb pull "$p" ~/onezero-apk/; done
   ```

   (`il.co.firstdigitalbank` = "The First Digital Bank" = OneZero → `tfd-bank`.)

2. **Extract the two PEM resources** from `base.apk` (an APK is a zip):

   ```bash
   cd ~/onezero-apk
   unzip -o -j base.apk 'res/raw/mtls_cert.pem' 'res/raw/mtls_key.key' -d mtls
   ```

3. **Verify** it's the right cert and that the edge accepts it:

   ```bash
   openssl x509 -in mtls/mtls_cert.pem -noout -subject -issuer -dates
   curl -sS -o /dev/null -w "%{http_code}\n" \
     --cert mtls/mtls_cert.pem --key mtls/mtls_key.key \
     -X POST https://identity.tfd-bank.com/v1/devices/token \
     -H 'Content-Type: application/json' --data '{"extClientId":"mobile","os":"Android"}'
   ```

   Expect `200` (a JSON response), not `403`. If you still get `403`, the app
   may have added a second factor beyond mTLS — re-inspect the app's
   `AuthHeaderInterceptor` (`na0`, see the decompile note below) before
   proceeding.

4. **Vendor the new files** into the repo (overwriting the old ones):

   ```bash
   cp ~/onezero-apk/mtls/mtls_cert.pem \
      scraper/providers/banks/onezero_mtls/mtls_cert.pem
   cp ~/onezero-apk/mtls/mtls_key.key \
      scraper/providers/banks/onezero_mtls/mtls_key.key
   ```

   Commit them. Done.

### Where the cert lives inside the app (for re-analysis after a rotation)

`jadx -d src base.apk`, then read `CloudFlareUseCase.kt` / `hx1` and
`TrustCertificateUseCase.kt` / `opb` — they load `R.raw.mtls_key` +
`R.raw.mtls_cert` and install them as an OkHttp `KeyManager`. The auth
requests' headers come from `AuthHeaderInterceptor.kt` / `na0` (currently the
client cert alone is sufficient — the extra headers were not needed to pass
the WAF; re-check here if a future rotation adds a header requirement). The
custom User-Agent format is `ONEZEROIL/<ver>(<build>) Lokalize/<n> <device> MTLS`.

## Terms of service

Replaying the app's client certificate is further over the line than
mimicking the app's requests. It's used here for the account owner scraping
their own data. That's the user's call to make, not a default.
