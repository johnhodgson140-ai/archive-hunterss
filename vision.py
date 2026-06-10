import requests
from PIL import Image
import imagehash
import io

HEADERS = {"User-Agent": "ArchiveHunterBot/1.0"}


def fetch_image(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def compute_phash_from_bytes(bts):
    try:
        img = Image.open(io.BytesIO(bts)).convert('RGB')
        h = imagehash.phash(img)
        return str(h)
    except Exception:
        return None


def compute_phash(url):
    b = fetch_image(url)
    if not b:
        return None
    return compute_phash_from_bytes(b)


def hamming_distance(hash1, hash2):
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return (h1 - h2)
    except Exception:
        return 999
