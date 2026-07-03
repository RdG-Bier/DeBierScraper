name: Scrape en publiceer

on:
  schedule:
    - cron: "0 5 * * *"   # dagelijks 05:00 UTC (= 06:00/07:00 NL)
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
