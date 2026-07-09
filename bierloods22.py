name: Scrape en publiceer

on:
  schedule:
    # GitHub-cron werkt in UTC. Nederland is in de zomer UTC+2:
    # 03:00 UTC = 05:00 NL | 09:30 UTC = 11:30 NL | 15:30 UTC = 17:30 NL
    # (in de winter schuiven deze een uur op naar 04:00/10:30/16:30 NL)
    - cron: "0 3 * * *"
    - cron: "30 9 * * *"
    - cron: "30 15 * * *"
  workflow_dispatch:        # handmatige 'Refresh'-knop in GitHub (ook mobiel)

permissions:
  contents: write

concurrency:
  group: scrape
  cancel-in-progress: false

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 300
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      # cache van opgehaalde pagina's bewaren tussen runs (minder belasting shops)
      - uses: actions/cache@v4
        with:
          path: cache
          key: scraper-cache-${{ github.run_id }}
          restore-keys: scraper-cache-

      - run: pip install -r requirements.txt

      - run: python main.py

      - name: Resultaat committen (docs/)
        run: |
          git config user.name "bierscraper-bot"
          git config user.email "actions@github.com"
          git add docs/
          git diff --cached --quiet || git commit -m "Bieroverzicht bijgewerkt $(date +'%d-%m-%Y %H:%M')"
          git push
