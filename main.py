"""
Entry point for building the combined XMLTV guide (``guide.xml``).

This script:

1. Loads the channel configuration (``channels.json``).
2. Fetches programme data per channel from the public schedule APIs via the
   provider modules in ``src/providers`` (Sky, Freeview, Freesat, Radio
   Times, YouView).
3. Deduplicates and serialises those into an XMLTV tree.
4. Merges in external XMLTV guides (Rytec Sky Live + Sport/Movies) so premium
   channels (Sky Sports, Sky Cinema, TNT, etc.) that the public APIs don't
   expose are covered too.
5. Writes a single ``guide.xml`` (and ``guide.xml.gz``) atomically.

Everything runs from code in this repository — no external repos are cloned
at runtime. Usage:

    python main.py

Set ``LOGLEVEL`` (e.g. ``LOGLEVEL=DEBUG``) to change verbosity.
"""

import gzip
import logging
import os

import pytz
from lxml import etree

from src.config import load_channels
from src.dedupe import dedupe_programmes
from src.http import make_session
from src.merge import merge_external
from src.xmltv import build_xmltv, write_atomic
from src.providers import sky, freeview, freesat, radiotimes, youview
from src.providers.base import Context

logger = logging.getLogger(__name__)

OUTPUT = "guide.xml"

FETCHERS = {
    "sky": sky.fetch_programmes,
    "freeview": freeview.fetch_programmes,
    "freesat": freesat.fetch_programmes,
    "rt": radiotimes.fetch_programmes,
    "yv": youview.fetch_programmes,
}


def main() -> None:
    channels = load_channels("channels.json")
    session = make_session()
    ctx = Context(session=session, tz=pytz.timezone("Europe/London"), days=7, caches={})

    programmes = []
    for channel in channels:
        fetcher = FETCHERS.get(channel.get("src"))
        if fetcher is None:
            logger.warning(
                "Unknown source '%s' for channel %s; skipping.",
                channel.get("src"), channel.get("name"),
            )
            continue
        try:
            programmes.extend(fetcher(channel, ctx))
        except Exception as exc:
            logger.error("Error fetching %s: %s", channel.get("name"), exc)

    programmes = dedupe_programmes(programmes)
    logger.info("Scraped %d programmes across %d channels", len(programmes), len(channels))

    # Serialise our scraped guide, then merge external XMLTV (Rytec) into it.
    xml_bytes = build_xmltv(channels, programmes, tz=ctx.tz)
    root = etree.fromstring(xml_bytes, parser=etree.XMLParser(huge_tree=True))
    ext_ch, ext_pr = merge_external(root, session)
    logger.info("Merged %d external channels and %d external programmes", ext_ch, ext_pr)

    final = etree.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True)
    write_atomic(OUTPUT, final)
    with gzip.open(OUTPUT + ".gz", "wb") as f:
        f.write(final)

    total_ch = len(root.findall("channel"))
    total_pr = len(root.findall("programme"))
    logger.info("Wrote %s: %d channels, %d programmes", OUTPUT, total_ch, total_pr)


if __name__ == "__main__":
    loglevel = os.environ.get("LOGLEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, loglevel, logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    main()
