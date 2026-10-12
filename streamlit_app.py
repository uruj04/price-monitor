"""Browser-based live demo for the Playwright Price Monitor."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from pricemonitor.alerts import build_alerts
from pricemonitor.config import Settings
from pricemonitor.exceptions import PriceMonitorError
from pricemonitor.models import Product
from pricemonitor.scraper import PriceScraper


st.set_page_config(page_title="Price Monitor", page_icon="🏷️", layout="centered")

st.title("Price Monitor")
st.caption("Check a public product page with the project's Playwright browser automation.")
st.info(
    "Use only pages you are permitted to monitor. Some stores block automated requests or do not "
    "allow scraping in their terms of use."
)

with st.form("product"):
    name = st.text_input("Product name", value="A Light in the Attic")
    url = st.text_input(
        "Product URL",
        value="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    )
    selector = st.text_input("Price CSS selector", value="div.product_main p.price_color")
    target = st.text_input("Optional target price", placeholder="Example: 50.00")
    submitted = st.form_submit_button("Check current price", type="primary")

if not submitted:
    st.stop()

if not name.strip() or not url.startswith(("https://", "http://")) or not selector.strip():
    st.error("Enter a product name, a valid http(s) URL, and a CSS selector for the price.")
    st.stop()

try:
    target_price = float(target) if target.strip() else None
    if target_price is not None and target_price <= 0:
        raise ValueError
except ValueError:
    st.error("Target price must be a positive number.")
    st.stop()

product = Product(
    name=name.strip(),
    url=url.strip(),
    price_selector=selector.strip(),
    target_price=target_price,
)

with tempfile.TemporaryDirectory() as directory:
    work_dir = Path(directory)
    settings = Settings(
        headless=True,
        timeout_ms=15_000,
        max_retries=2,
        retry_delay_s=1.0,
        screenshot_dir=work_dir / "screenshots",
        data_file=work_dir / "price_history.csv",
        log_file=work_dir / "price_monitor.log",
    )

    try:
        with st.spinner("Opening a browser and reading the price..."):
            with PriceScraper(settings) as scraper:
                reading = scraper.check(product)
    except PriceMonitorError as exc:
        st.error(str(exc))
        st.stop()

    st.success("Price checked successfully.")
    price, raw = st.columns(2)
    price.metric("Current price", f"{reading.price:.2f}")
    raw.write(f"**Displayed value:** {reading.raw_text}")
    st.write(f"**Checked:** {reading.timestamp}")

    alerts = build_alerts(product, reading, previous_price=None)
    for alert in alerts:
        st.warning(alert)

    screenshot = Path(reading.screenshot)
    if screenshot.is_file():
        st.image(screenshot.read_bytes(), caption="Browser screenshot captured during this check")

st.caption("This demo processes the requested check only. It does not retain product data, history, or screenshots after the session ends.")
