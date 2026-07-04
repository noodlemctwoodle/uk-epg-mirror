"""
Re-key the merged guide to the IPTV service's own channel identifiers.

The scraped/merged guide is keyed by each source's own channel ids (e.g.
``SkyAtlantic.uk``, ``UAndDave.uk``). But the channels on the IPTV service carry
their own tvg-ids and names (e.g. tvg-id ``alibi.uk``, name ``Dave | FHD |``),
which rarely match those source ids exactly — so a player's fuzzy matcher
misses many of them.

This module rebuilds the guide keyed to the *service's* channel identity, so any
player on the same service matches by exact tvg-id (or exact display-name) with
no fuzzy matching. The service's channel list lives in ``provider_channels.json``
(a snapshot: name + tvg_id + group), and a small hand-maintained ``aliases.json``
resolves known id-convention differences (``dave.uk`` -> ``UAndDave.uk``, etc.).

Resolution order per service channel: alias (by tvg-id or name) -> exact source
tvg-id -> normalized display-name (prefer the source feed with the most
programmes). Channels that resolve to no source feed are dropped (no data
exists for them anywhere).
"""

import json
import logging
import re
from lxml import etree

logger = logging.getLogger(__name__)

_QUALITY = re.compile(r"\b(fhd|uhd|hd|sd|4k|nowtv|now tv|catchup|catch up|backup|plus1)\b")
_REGION_PREFIX = re.compile(r"^(uk|us|usa|ca|au|ie|de|fr|es|it|gr|ro|pl|in|za|nz|pt|nl|dk|se|no)\s*[:]")


def norm(name: str) -> str:
    """Normalize a channel name for matching: drop ``| ... |`` tags, quality
    words, region prefixes, and non-alphanumerics."""
    if not name:
        return ""
    s = re.sub(r"\|[^|]*\|", " ", name).replace("|", " ").lower()
    s = _QUALITY.sub(" ", s)
    s = _REGION_PREFIX.sub(" ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _slug(name: str) -> str:
    return "svc-" + re.sub(r"[^a-z0-9]", "", (name or "").lower())


def rekey(root, provider_channels, aliases):
    """Rebuild ``root`` (a parsed ``<tv>``) keyed to the service's channels.

    Returns ``(new_root, matched, total)``.
    """
    # Index the source guide.
    src_ids = {}                     # lowercased source id -> original source id
    src_progs = {}                   # source id -> [<programme> elements]
    for ch in root.findall("channel"):
        cid = ch.get("id")
        if cid:
            src_ids[cid.lower()] = cid
    for pr in root.findall("programme"):
        src_progs.setdefault(pr.get("channel"), []).append(pr)

    name_idx = {}                    # normalized display-name -> (source id, programme count)
    for ch in root.findall("channel"):
        cid = ch.get("id")
        k = norm(ch.findtext("display-name") or "")
        if not k:
            continue
        cnt = len(src_progs.get(cid, []))
        if k not in name_idx or cnt > name_idx[k][1]:
            name_idx[k] = (cid, cnt)

    aliases = {k.lower(): v for k, v in (aliases or {}).items()}

    def resolve(name, tvg):
        tvg_l = (tvg or "").strip().lower()
        if tvg_l and tvg_l in aliases:
            return aliases[tvg_l]
        if name and name.lower() in aliases:
            return aliases[name.lower()]
        if tvg_l and tvg_l in src_ids:
            return src_ids[tvg_l]
        k = norm(name)
        if k in name_idx:
            return name_idx[k][0]
        return None

    # One service key per channel (tvg-id if present, else name slug).
    keymap = {}                      # service key -> (source id, display-name)
    for pc in provider_channels:
        name = pc.get("name") or ""
        tvg = (pc.get("tvg_id") or "").strip()
        src = resolve(name, tvg)
        if not src:
            continue
        key = tvg if tvg else _slug(name)
        keymap.setdefault(key, (src, name))

    # Append provider-keyed <channel> aliases (+ programme copies) to the source
    # guide rather than replacing it: the source channels stay so a player's
    # fuzzy matcher can still catch channels we didn't key, while these aliases
    # guarantee an exact tvg-id/name match for the ones we did.
    existing = {c.get("id") for c in root.findall("channel")}
    added = 0
    for key, (src, dispname) in sorted(keymap.items()):
        if key in existing:
            continue
        ce = etree.SubElement(root, "channel")
        ce.set("id", key)
        etree.SubElement(ce, "display-name").text = dispname
        existing.add(key)
        added += 1
        for pr in src_progs.get(src, []):
            np = etree.fromstring(etree.tostring(pr))
            np.set("channel", key)
            root.append(np)

    return root, added, len(provider_channels)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("%s not found; skipping.", path)
        return default
