# -*- coding: utf-8 -*-
"""
Vangnet per shop. Levert een shop ineens niets of minder dan de helft van de
vorige keer (storing, blokkade, gewijzigde website), dan blijven de gegevens
van de vorige geslaagde ronde staan en verschijnt er een waarschuwing op de
pagina. Zo valt een tabblad niet zomaar leeg.

Duurt de afwijking langer dan config.VANGNET_MAX_UREN, dan accepteren we de
nieuwe situatie (de shop kan echt kleiner zijn geworden).
"""

import json
import logging
import time
from pathlib import Path

import config

log = logging.getLogger("bierscraper")
DOCS = Path(__file__).parent / "docs"
STATUS_FILE = DOCS / "status.json"


def laad_status():
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bewaar_status(status):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")


def controleer(site, beers, status, nu=None):
    """Geeft (te_gebruiken_bieren, vangnet_actief) terug en zet bij een actief
    vangnet site["_waarschuwing"]."""
    nu = nu or time.time()
    key = site["key"]
    try:
        vorige = json.loads((DOCS / f"raw_{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vorige = []
    st = status.setdefault(key, {})
    n_nu, n_vorig = len(beers), len(vorige)
    verdacht = n_vorig >= config.VANGNET_MIN_AANTAL and n_nu < 0.5 * n_vorig

    if verdacht:
        sinds = st.get("verdacht_sinds") or nu
        st["verdacht_sinds"] = sinds
        if nu - sinds < config.VANGNET_MAX_UREN * 3600:
            laatst_goed = (time.strftime("%d-%m %H:%M", time.localtime(st["ok_ts"]))
                           if st.get("ok_ts") else "de vorige ronde")
            site["_waarschuwing"] = (
                "de laatste ophaalronde gaf %d bieren (was %d); de gegevens van %s "
                "blijven staan" % (n_nu, n_vorig, laatst_goed))
            log.warning("%s: VANGNET actief - %s", site["label"], site["_waarschuwing"])
            return vorige, True
        log.warning("%s: afwijking duurt langer dan %d uur; nieuwe situatie geaccepteerd "
                    "(%d bieren, was %d)", site["label"], config.VANGNET_MAX_UREN, n_nu, n_vorig)

    st.pop("verdacht_sinds", None)
    st["ok_ts"], st["ok_n"] = nu, n_nu
    return beers, False
