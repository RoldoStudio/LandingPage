import argparse
import hashlib
import os
import re
import sys
import urllib.parse
import urllib.request


IMAGE_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}


def extract_img_srcs(html_text: str) -> list[str]:
    urls = []
    for match in re.finditer(r"<img\b[^>]*\bsrc=(['\"])(.*?)\1", html_text, flags=re.IGNORECASE):
        url = match.group(2).strip()
        if url:
            urls.append(url)
    return urls


def guess_extension(url: str, content_type: str | None) -> str:
    if content_type:
        base_content_type = content_type.split(";", 1)[0].strip().lower()
        if base_content_type in IMAGE_EXT_BY_CONTENT_TYPE:
            return IMAGE_EXT_BY_CONTENT_TYPE[base_content_type]

    parsed = urllib.parse.urlparse(url)
    _, ext = os.path.splitext(parsed.path)
    ext = ext.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
        return ".jpg" if ext == ".jpeg" else ext

    return ".jpg"


def filename_for_url(url: str, ext: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"img_{digest}{ext}"


def download(url: str, target_path: str, timeout_seconds: int) -> tuple[bool, str | None]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        content_type = response.headers.get("Content-Type")
        data = response.read()

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "wb") as f:
        f.write(data)

    return True, content_type


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=os.getcwd(),
        help="Directorio raíz donde están los .html (por defecto: directorio actual).",
    )
    parser.add_argument(
        "--images-dir",
        default="images",
        help="Carpeta destino para imágenes (relativa a --root).",
    )
    parser.add_argument(
        "--html",
        nargs="*",
        default=["index.html", "about_us.html", "contact.html"],
        help="Lista de archivos HTML a procesar (relativos a --root).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout en segundos para cada descarga.",
    )
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    images_dir = os.path.join(root, args.images_dir)
    html_paths = [os.path.join(root, p) for p in args.html]

    url_to_local: dict[str, str] = {}
    all_urls: list[str] = []

    for html_path in html_paths:
        if not os.path.isfile(html_path):
            continue
        with open(html_path, "r", encoding="utf-8") as f:
            html_text = f.read()
        all_urls.extend(extract_img_srcs(html_text))

    unique_urls = []
    seen = set()
    for url in all_urls:
        if not url.lower().startswith(("http://", "https://")):
            continue
        if url in seen:
            continue
        seen.add(url)
        unique_urls.append(url)

    downloaded_count = 0
    skipped_existing = 0
    failed = 0

    for url in unique_urls:
        temp_ext = guess_extension(url, None)
        provisional_name = filename_for_url(url, temp_ext)
        provisional_path = os.path.join(images_dir, provisional_name)

        if os.path.exists(provisional_path):
            url_to_local[url] = f"{args.images_dir}/{provisional_name}".replace("\\", "/")
            skipped_existing += 1
            continue

        try:
            ok, content_type = download(url, provisional_path, args.timeout)
            if not ok:
                failed += 1
                continue

            final_ext = guess_extension(url, content_type)
            final_name = filename_for_url(url, final_ext)
            final_path = os.path.join(images_dir, final_name)

            if final_path != provisional_path:
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                if os.path.exists(final_path):
                    os.remove(provisional_path)
                else:
                    os.replace(provisional_path, final_path)

            url_to_local[url] = f"{args.images_dir}/{final_name}".replace("\\", "/")
            downloaded_count += 1
        except Exception:
            failed += 1

    rewritten_files = 0
    for html_path in html_paths:
        if not os.path.isfile(html_path):
            continue
        with open(html_path, "r", encoding="utf-8") as f:
            original = f.read()
        updated = original
        for url, local in url_to_local.items():
            updated = updated.replace(url, local)
        if updated != original:
            with open(html_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(updated)
            rewritten_files += 1

    print(f"Imágenes encontradas: {len(unique_urls)}")
    print(f"Descargadas: {downloaded_count}")
    print(f"Ya existían: {skipped_existing}")
    print(f"Fallidas: {failed}")
    print(f"HTML actualizados: {rewritten_files}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

