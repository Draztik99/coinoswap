# CoinoSwap Daily Rates — preparation only

This project validates and generates a branded daily price image. **It cannot post to Facebook, Instagram or YouTube.** Publishing remains separately controlled by the ChatGPT–Metricool workflow.

## Before deployment

1. Upload the original supplied 1536×1024 PNG to `daily-rates/assets/coinoswap_template.png` on the `feature/daily-rates-cloud` branch.
2. In GitHub **Settings → Secrets and variables → Actions**, add repository secret `CMC_API_KEY` with the existing CoinMarketCap key. Do not share or commit the key.
3. In GitHub **Settings → Actions → General**, allow workflow **Read and write permissions** so the workflow can commit the new assets.
4. Review the draft pull request. Do not merge or enable scheduling until these dependencies are complete.
5. A valid scheduled run starts at 11:50 SAST, checks CoinMarketCap and Kraken, requires quotations <=5 minutes old, and enforces <=1% BTC/ETH and <=2% XMR deviations.
6. The output is `docs/daily-rates/YYYY-MM-DD.png` and `.json`, with sources, timestamps and a SHA-256 digest. The social media scheduler still needs to retrieve and independently check both artifacts.
7. GitHub scheduled runs may be delayed. This code **fails closed** if it starts after 11:56 SAST, rather than publish unverified prices.

## Important publishing limitation

The free Metricool plan has monthly scheduling limits; a permanent 30–31 day daily service will require an appropriate publisher. Do not interpret this working image-preparation workflow as end-to-end posting success.

## Example files after a successful run

https://raw.githubusercontent.com/Draztik99/coinoswap/main/docs/daily-rates/YYYY-MM-DD.png

https://raw.githubusercontent.com/Draztik99/coinoswap/main/docs/daily-rates/YYYY-MM-DD.json

**Not yet deployed. Do not merge a partial staging branch.**
