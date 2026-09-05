"""Verifies the ranged firmware endpoint end to end, without a device.

Pulls /v1/vehicle/firmware/latest the way the firmware does -- one 32 KiB Range
request at a time -- reassembles the image and checks it against the x-MD5 the
server advertised, plus each chunk against its x-Chunk-MD5. Then re-fetches the
whole image without a Range header and checks the two agree.

That splits the "MD5 Check Failed" the device reports into one of:
  * the server's own bytes and digest disagree      -> backend bug
  * ranged and unranged bytes differ                -> Range slicing bug
  * both fine here                                  -> corruption on the device

    python check_ota_ranges.py https://api.vat.druenert.com <imei> <password>
"""
import hashlib
import sys

import requests

CHUNK = 32 * 1024
PATH = "/v1/vehicle/firmware/latest"


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2

    base, imei, password = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    auth = (imei, password)
    url = base + PATH

    first = requests.get(url, auth=auth, headers={"Range": f"bytes=0-{CHUNK - 1}"}, timeout=60)
    if first.status_code == 204:
        print("204: no update pending for this device. Issue one first.")
        return 1
    if first.status_code != 206:
        print(f"expected 206, got {first.status_code}. Range support is not reaching the app.")
        print(f"  headers: {dict(first.headers)}")
        return 1

    total = int(first.headers["Content-Range"].rsplit("/", 1)[1])
    advertised = first.headers.get("x-MD5", "").lower()
    print(f"total {total} B, advertised whole-image MD5 {advertised}")

    parts = []
    bad_chunks = []
    offset = 0
    resp = first

    while True:
        body = resp.content
        chunk_md5 = resp.headers.get("x-Chunk-MD5", "").lower()
        actual = hashlib.md5(body).hexdigest()

        if chunk_md5 and chunk_md5 != actual:
            bad_chunks.append((offset, chunk_md5, actual))

        expected_len = min(CHUNK, total - offset)
        if len(body) != expected_len:
            print(f"  ! chunk at {offset}: got {len(body)} B, expected {expected_len} B")

        parts.append(body)
        offset += len(body)
        if offset >= total:
            break

        end = min(offset + CHUNK, total) - 1
        resp = requests.get(url, auth=auth, headers={"Range": f"bytes={offset}-{end}"}, timeout=60)
        if resp.status_code != 206:
            print(f"  ! chunk {offset}-{end} returned {resp.status_code}")
            return 1

    ranged = b"".join(parts)
    ranged_md5 = hashlib.md5(ranged).hexdigest()

    print(f"\nreassembled {len(ranged)} B from {len(parts)} chunks, MD5 {ranged_md5}")
    print(f"  per-chunk digests    : {'all match' if not bad_chunks else str(len(bad_chunks)) + ' MISMATCH'}")
    for off, want, got in bad_chunks:
        print(f"      offset {off}: header {want} vs actual {got}")
    print(f"  vs advertised x-MD5  : {'MATCH' if ranged_md5 == advertised else 'MISMATCH'}")

    whole = requests.get(url, auth=auth, timeout=300)
    if whole.status_code == 200:
        whole_md5 = hashlib.md5(whole.content).hexdigest()
        print(f"\nunranged download {len(whole.content)} B, MD5 {whole_md5}")
        print(f"  vs advertised x-MD5  : {'MATCH' if whole_md5 == advertised else 'MISMATCH'}")
        print(f"  vs ranged reassembly : {'MATCH' if whole_md5 == ranged_md5 else 'MISMATCH'}")
        if whole.content != ranged:
            for i, (a, b) in enumerate(zip(whole.content, ranged)):
                if a != b:
                    print(f"  first differing byte at {i} (chunk {i // CHUNK}, "
                          f"offset {i % CHUNK} within it): unranged {a:#04x} vs ranged {b:#04x}")
                    break
    else:
        print(f"\nunranged download returned {whole.status_code}")

    ok = ranged_md5 == advertised and not bad_chunks
    print("\n=> server side is consistent; look at the device"
          if ok else "\n=> the server is serving bytes that do not match its own digest")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
