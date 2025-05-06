import asyncio
import httpx
from pathlib import Path
import re
# Attempt to import the specific libgen-api.
# If this exact import fails, you may need to investigate the
# harrison-broadbent/libgen-api library structure to find the correct import.
from libgen_api import LibgenSearch

from rich import print
# --- Configuration ---
BOOK_TITLES: list[str] = [
    "The Women",
    "Funny Story",
    "First Lie Wins",
    "Just for the Summer",
    "When the Moon Hatched",
    "The Familiar",
    "We Solve Murders",
    "The Book of Doors",
    "I Cheerfully Refuse",
    "You are Here",
    "The Reappearance of Rachel Price",
    "Martyr",
    "Deep End",
    "The Husbands",
    "Blue Sisters",
    "Sandwich",
    "A Fate Inked in Blood",
    "Heartless Hunter",
    "Water Moon",
    "Beautiful Ugly",
    "The Three Lives of Cate Kay",
    "All the Colours of the Dark",
    "Burn",
    "The Warm Hands of Ghosts",
    "The Tainted Cup",
    "The Grandest Game",
    "The God of the Woods",
    "The Mercy of Gods",
    "Where the Dark Stands Still",
    "Witchcraft for Wayward Girls",
]

DOWNLOAD_ROOT = Path("downloaded_books")
MAX_CONCURRENT_DOWNLOADS = 5 # Adjust as needed, be respectful to servers
REQUEST_TIMEOUT = 30  # seconds

# Preferred mirrors (order matters, will try the first one found)
# Common LibGen mirrors. You might need to adjust this list based on what the API returns or current mirror availability.
PREFERRED_MIRRORS_KEYS = ["GET", "Cloudflare", "IPFS.io", "Libgen.rs", "Libgen.li"]

import diskcache

cache = diskcache.Cache("libgen_cache")

def sanitize_filename(title_input: str) -> str:
    """Sanitizes a string to be a valid filename."""
    s = str(title_input) # Ensure it's a string
    s = re.sub(r'[\\/*?:"<>|]',"", s)
    s = s.replace(" ", "_")
    return s[:150] # Limit length


# @cache.memoize(ignore=[1])
async def get_download_info(title: str, lg_search: LibgenSearch) -> dict | None:
    """Searches for a book and tries to get a direct download link."""
    print(f"[INFO] Searching for: {title}")
    try:
        results = lg_search.search_title_filtered(title, {"extension": "epub"}, exact_match=False)
        if not results:
            results = lg_search.search_title(title) # Fallback to general title search

        if not results:
            print(f"[WARN] No results found for: {title}")
            return None

        item = results[0]

        download_links = lg_search.resolve_download_links(item)

        if not download_links:
             if isinstance(item, dict) and "mirrors" in item:
                 download_links = item["mirrors"]
             else:
                 download_links = item

        if not download_links or not isinstance(download_links, dict):
            print(f"[WARN] No download links found or in unexpected format for: {title}")
            return None

        chosen_url = None
        raw_extension = item.get("extension", "epub")
        file_extension = str(raw_extension) if raw_extension is not None else "epub"

        for mirror_key in PREFERRED_MIRRORS_KEYS:
            if mirror_key in download_links and isinstance(download_links.get(mirror_key), str):
                chosen_url = download_links[mirror_key]
                print(f"[INFO] Found mirror '{mirror_key}' for {title}")
                break

        if not chosen_url:
            if download_links:
                for potential_url in download_links.values():
                    if isinstance(potential_url, str):
                        chosen_url = potential_url
                        print(f"[INFO] Using first available string mirror for {title}")
                        break

        if chosen_url:
            # Ensure the title used for filename is a simple string.
            raw_original_title = item.get("title", title) # title here is the search term (string)
            original_title_for_filename = str(raw_original_title) if raw_original_title is not None else title

            filename = f"{sanitize_filename(original_title_for_filename)}.{file_extension}"
            # The 'title' in the returned dict can be the more descriptive one from item if it's a string
            display_title = str(raw_original_title) if isinstance(raw_original_title, str) else title
            return {"title": display_title, "url": chosen_url, "filename": filename}
        else:
            print(f"[WARN] Could not select a download URL for: {title}")
            return None

    except Exception as e:
        print(f"[ERROR] Exception while searching for {title}: {e}")
        return None


async def download_book(session: httpx.AsyncClient, url: str, filepath: Path, semaphore: asyncio.Semaphore):
    """Downloads a single book asynchronously."""
    async with semaphore:
        print(f"[INFO] Attempting to download: {filepath.name} from {url}")
        try:
            async with session.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(filepath, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
                print(f"[SUCCESS] Downloaded: {filepath.name}")
        except httpx.HTTPStatusError as e:
            print(f"[ERROR] HTTP error downloading {filepath.name}: {e.response.status_code} - {e.request.url}")
        except httpx.RequestError as e:
            print(f"[ERROR] Request error downloading {filepath.name}: {e}")
        except Exception as e:
            print(f"[ERROR] General error downloading {filepath.name}: {e}")


async def main():
    if not BOOK_TITLES:
        print("[ERROR] The BOOK_TITLES list is empty. Please add book titles to download.")
        return

    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    lg_search = LibgenSearch()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    async def throttled_get_download_info(title_search_term):
        async with semaphore:
            cache_key = f"download_info_{title_search_term}"
            res = cache.get(cache_key)
            if res is None:
                res = await get_download_info(title_search_term, lg_search)
                cache.set(cache_key, res, expire=60*60*24) # Cache for 24 hours
            print(res)
            return res
    book_infos = await asyncio.gather(*[throttled_get_download_info(title_search_term) for title_search_term in BOOK_TITLES])
    print(book_infos)

    exit()
    # exit()

    async with httpx.AsyncClient() as session:
        tasks = []
        for title_search_term in BOOK_TITLES:
            if download_info:
                filepath = DOWNLOAD_ROOT / download_info["filename"]
                if filepath.exists():
                    print(f"[INFO] File already exists, skipping: {filepath.name}")
                    continue
                tasks.append(
                    download_book(
                        session,
                        download_info["url"],
                        filepath,
                        semaphore,
                    )
                )

        if tasks:
            # Correctly escape newline for f-string if it was the issue
            print(f"\n[INFO] Starting {len(tasks)} downloads...")
            await asyncio.gather(*tasks)
        else:
            print("[INFO] No books to download (either all exist or none were found).")

    # Correctly escape newline for f-string
    print(f"\n[INFO] Download process finished.")
    print(f"Books are in: {DOWNLOAD_ROOT.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())