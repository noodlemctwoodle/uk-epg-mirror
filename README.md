# uk-epg-mirror

A single, self-contained XMLTV EPG builder. All the code needed to build the
guide lives in this repo — nothing is cloned from other repositories at
runtime. A GitHub Action runs it every 12 hours and publishes the result as a
Release asset (stable URL, no git-history bloat).

## Output

One combined, gzipped guide at a stable URL:

- `https://github.com/noodlemctwoodle/uk-epg-mirror/releases/latest/download/guide.xml.gz`

Point your EPG source (e.g. Dispatcharr) at that URL. It auto-detects gzip.
Channels are matched by their `tvg-id` / display name.

## How it works

`python main.py`:

1. Reads `channels.json` (the list of channels to build, each with a `src`
   and a source-specific id).
2. Fetches programme schedules per channel from public provider APIs
   (`src/providers/`):
   - **sky** — `awk.epgsky.com` linear schedule API (the bulk of UK linear:
     BBC, ITV, Channel 4/5, entertainment, kids, music, news, TNT Sports…)
   - **freeview**, **freesat**, **rt** (Radio Times), **yv** (YouView) —
     fallback schedule APIs for channels not on Sky's public feed.
3. Deduplicates and serialises those into XMLTV.
4. Merges in the **Rytec** UK/Ireland guides (`src/merge.py`), decompressed
   from `xmltvepg.nl`, to cover premium channels the public APIs don't expose
   (Sky Sports, Sky Cinema, Premier Sports, Viaplay…).
5. Writes `guide.xml` + `guide.xml.gz`.

## Coverage

Covers the linear/broadcast channels that have an obtainable schedule
(hundreds of UK channels). Event-only sports feeds (PPV, per-event numbered
channels) and adult channels have no published schedule anywhere and are not
covered by any EPG source.

## Adding channels

Edit `channels.json`. Each entry:

```json
{ "name": "BBC One", "src": "sky", "provider_id": "2091", "xmltv_id": "bbc1.uk", "lang": "en", "icon_url": "..." }
```

## Credits & licence

The scraper engine (`src/`, `channels.json`, provider modules) is derived
from [dp247/Freeview-EPG](https://github.com/dp247/Freeview-EPG), licensed
under **GPLv3** — see `LICENSE` and `NOTICE`. This repository is therefore
also distributed under GPLv3. Programme data belongs to its respective
providers; this project only reformats publicly available schedule data.
