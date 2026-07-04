"""
Merge external XMLTV guides into our scraped guide.

Some channels (notably Sky Sports, Sky Cinema and other premium/movie
services) are not available from the public schedule APIs used by the
scraper providers. For those we fold in the Rytec UK/Ireland XMLTV guides,
which are published as ``.xz``-compressed XMLTV. We decompress them with the
standard-library ``lzma`` module (no external ``xz`` binary required) and
append their ``<channel>`` and ``<programme>`` elements to our own tree.

External guides are treated as opaque XMLTV passthroughs: we do not
reinterpret their timestamps, we simply carry their elements across. Channel
entries whose ``id`` we already have are skipped so our own (cleaner)
definitions win.
"""

import logging
import lzma
from typing import List

from lxml import etree

logger = logging.getLogger(__name__)

# Rytec UK/Ireland guides. Sky Live carries the bulk of Sky-numbered linear
# channels; Sport & Movies carries Sky Sports, Sky Cinema, TNT Sports,
# Premier Sports, Viaplay, etc.
RYTEC_SOURCES = [
    "http://www.xmltvepg.nl/rytecUK_SkyLive.xz",
    "http://www.xmltvepg.nl/rytecUK_SportMovies.xz",
]


def fetch_xmltv_xz(session, url: str) -> bytes:
    """Download an ``.xz``-compressed XMLTV file and return decompressed bytes."""
    resp = session.get(url, timeout=(10, 90))
    resp.raise_for_status()
    return lzma.decompress(resp.content)


def _parse(data: bytes):
    """Parse XMLTV bytes into a root element, tolerating minor malformations."""
    parser = etree.XMLParser(recover=True, huge_tree=True)
    return etree.fromstring(data, parser=parser)


def merge_external(base_root, session, urls: List[str] = None):
    """Merge external XMLTV guides into ``base_root`` in place.

    Args:
        base_root: The ``<tv>`` root element of our scraped guide.
        session: A ``requests.Session`` for downloads.
        urls: List of ``.xz`` XMLTV URLs. Defaults to the Rytec guides.

    Returns:
        The number of channels and programmes added, as a ``(channels,
        programmes)`` tuple. Failures on any single source are logged and
        skipped so a flaky mirror never fails the whole build.
    """
    if urls is None:
        urls = RYTEC_SOURCES

    existing_ids = {
        c.get("id", "").lower() for c in base_root.findall("channel")
    }
    added_channels = 0
    added_programmes = 0

    for url in urls:
        try:
            data = fetch_xmltv_xz(session, url)
            ext_root = _parse(data)
        except Exception as exc:
            logger.error("Failed to fetch/parse external guide %s: %s", url, exc)
            continue

        for ch in ext_root.findall("channel"):
            cid = (ch.get("id") or "").lower()
            if not cid or cid in existing_ids:
                continue
            existing_ids.add(cid)
            base_root.append(ch)
            added_channels += 1

        for prog in ext_root.findall("programme"):
            base_root.append(prog)
            added_programmes += 1

        logger.info(
            "Merged %s: running totals %d channels, %d programmes",
            url, added_channels, added_programmes,
        )

    return added_channels, added_programmes
