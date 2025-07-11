# 
# OFFICIAL VERSION v1.5 (Final)
# This script builds on v1.4 and finalizes the stable release of the Echo Google Business Review Harvester.
#
# Confirmed Capabilities:
# - Stable scraping for businesses with up to ~300 reviews (confirmed through stress testing)
# - Full image extraction (review-uploaded photos only, not profile icons)
# - Clean filtering of owner replies, blank/deleted reviews, and UI noise
# - Structured fallbacks for missing or malformed review text
# - Headless mode toggle for faster, non-visual scraping
# - Outputs polished CSV + images with accurate metadata
#
# Known Limitations:
# - May stall or degrade above ~400 reviews
# - Review count comparison is currently manual (Verifier Tool pending)
# - May get stuck on loading spinners when attempting to scroll beyond ~300–400 reviews (review elements may not finish loading)
# - Reviews containing videos or multiple images with a "+" button are not fully captured; current scraper only retrieves visible first image
#
# Future Expansion:
# A Verifier Tool is planned to compare the CSV against the live review page, enabling scalable accuracy checks as review volume increases. This will allow trustable outputs even for datasets exceeding 500+ reviews.
# - Investigate workaround for infinite spinner/loading stall when scraping higher review counts (potential: timed scroll with exit trigger or detection of loading stall)
# - Add support for reviews that include videos or image sets behind "+2"/"+3" overlays — possibly by triggering thumbnail expansion or capturing links to media
#
import time
import os
import re
import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
from datetime import datetime
import urllib.request
def clean_final_text(raw_text):
    if not raw_text:
        return ""
    lowered = raw_text.lower()
    if "response from the owner" in lowered:
        return ""
    return raw_text.strip()


def launch_browser():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Use headless_mode from streamlit state if present, else default to False
    headless_mode = st.session_state.get("headless_mode", False)
    if headless_mode:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, use_subprocess=True)
    return driver


def main():
    st.title("Echo: Google Business Review Harvester")
    # Add headless mode checkbox at the top
    headless_mode = st.checkbox("Run in headless mode for faster scraping (no visible browser)", value=False, key="headless_mode")
    url = st.text_input("Enter the direct URL to the Google Maps business reviews page:")

    # Scraper logic runs only if not already scraped for this session and url is provided
    if url and "scraped" not in st.session_state:
        st.info("Launching browser...")
        driver = launch_browser()
        driver.get(url)
        st.info("🧭 Navigating to Google Business page... Please wait while the content loads.")

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'DU9Pgb'))  # Class for business name title
            )
            st.success("Page loaded successfully.")
            st.write("Page title:", driver.title)
        except Exception as e:
            st.error("❌ Failed to load the page. Please check the URL or internet connection.")
            driver.quit()
            return

        # Attempt to scroll and collect multiple reviews
        try:
            st.info("Scrolling to load all reviews...")
            scrollable_div = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "m6QErb") and contains(@class, "DxyBCb")]'))
            )
            scroll_attempts = 0
            max_scrolls = 60  # Safety cap
            last_review_count = 0
            stable_scrolls = 0

            while scroll_attempts < max_scrolls and stable_scrolls < 3:
                driver.execute_script("arguments[0].scrollTo(0, arguments[0].scrollHeight);", scrollable_div)
                time.sleep(2.5)
                review_cards = driver.find_elements(By.XPATH, '//div[@data-review-id]')
                if len(review_cards) == last_review_count:
                    stable_scrolls += 1
                else:
                    stable_scrolls = 0
                last_review_count = len(review_cards)
                scroll_attempts += 1

            st.success(f"Scrolling complete. Total scroll attempts: {scroll_attempts}")

            # Now extract all review cards
            review_cards = driver.find_elements(By.XPATH, '//div[@data-review-id]')

            # Expand all "More" buttons to get full text
            more_buttons = driver.find_elements(By.XPATH, '//button[contains(@class, "w8nwRe")]')
            for btn in more_buttons:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.1)
                except Exception:
                    continue

            # Filter duplicates by review-id (ensure uniqueness)
            unique_reviews = {}
            for card in review_cards:
                try:
                    review_id = card.get_attribute("data-review-id")
                    if review_id not in unique_reviews:
                        unique_reviews[review_id] = card
                except Exception:
                    continue

            st.write(f"🔍 Unique reviews found: {len(unique_reviews)}")

        except Exception as e:
            st.error(f"Error during scroll or extraction: {e}")

        # Export all collected reviews to CSV
        import pandas as pd
        from datetime import datetime, timedelta

        def parse_relative_date(date_text):
            today = datetime.today()
            match = re.search(r'\d+', date_text)
            if not match:
                return ""
            num = int(match.group())

            if "day" in date_text:
                return (today - timedelta(days=num)).date()
            elif "week" in date_text:
                return (today - timedelta(weeks=num)).date()
            elif "month" in date_text:
                return (today - timedelta(days=30 * num)).date()
            elif "year" in date_text:
                return (today - timedelta(days=365 * num)).date()
            else:
                return ""

        debug_mode = True  # Set to False to disable debug logging

        def is_valid_comment(text):
            if not text or len(text.strip()) < 5:
                return False
            lower = text.lower()
            if "response from the owner" in lower:
                return False
            # Remove typical punctuation and whitespace
            cleaned = re.sub(r"[^\w]", "", text)
            if not cleaned or len(cleaned) < 3:
                return False
            # If it ends with an ellipsis and contains no words, likely junk
            if text.strip().endswith("…") and not re.search(r"[a-zA-Z]", text):
                return False
            return True

        # Build review data list
        data = []
        for i, card in enumerate(unique_reviews.values()):
            reviewer = card.find_element(By.CLASS_NAME, 'd4r55').text
            rating = card.find_element(By.CLASS_NAME, 'kvMYJc').get_attribute('aria-label')
            try:
                try:
                    text = ""
                    source = "none"
                    if i < 29:
                        try:
                            wi_spans = card.find_elements(By.CLASS_NAME, 'wiI7pd')
                            temp_text = ""
                            for span in wi_spans:
                                try:
                                    span.find_element(By.XPATH, "./ancestor::div[contains(@class, 'CDe7pd')]")
                                    continue  # Skip if inside owner block
                                except:
                                    temp_text = span.text
                                    break
                            if is_valid_comment(temp_text):
                                text = temp_text
                                source = "wiI7pd"
                            else:
                                text = ""
                                source = "none"
                        except:
                            text = ""
                            source = "none"
                    else:
                        try:
                            wi_spans = card.find_elements(By.CLASS_NAME, 'wiI7pd')
                            temp_text = ""
                            for span in wi_spans:
                                try:
                                    span.find_element(By.XPATH, "./ancestor::div[contains(@class, 'CDe7pd')]")
                                    continue  # Skip if inside owner block
                                except:
                                    temp_text = span.text
                                    break
                            if is_valid_comment(temp_text):
                                text = temp_text
                                source = "wiI7pd"
                            else:
                                text = ""
                                source = "none"
                        except:
                            text = ""
                            source = "none"

                        if not text:
                            try:
                                review_id = card.get_attribute("data-review-id")
                                all_rfdo_spans = driver.find_elements(By.CLASS_NAME, 'RfDO5c')
                                fallback_spans = []
                                for span in all_rfdo_spans:
                                    try:
                                        parent = span.find_element(By.XPATH, "./ancestor::*[@data-review-id][1]")
                                        if parent.get_attribute("data-review-id") != review_id:
                                            continue
                                        # Reject span if it's inside an owner response block
                                        try:
                                            owner_ancestor = span.find_element(By.XPATH, "./ancestor::div[contains(@class, 'CDe7pd')]")
                                            continue  # Skip if inside owner reply
                                        except:
                                            fallback_spans.append(span)
                                    except:
                                        continue
                                text = " ".join(
                                    span.text for span in fallback_spans
                                    if span.text.strip() and "RfDO5c" not in (span.get_attribute("class") or "")
                                )
                                fallback_count = len(fallback_spans)
                                source = "rfdo_global"
                            except:
                                text = ""
                                fallback_count = 0
                                source = "none"

                            # New structural fallback
                            if not text:
                                try:
                                    rating_el = card.find_element(By.CLASS_NAME, 'kvMYJc')
                                    container = rating_el.find_element(By.XPATH, "./ancestor::div[@data-review-id][1]")
                                    # Find and skip the CDe7pd owner reply block
                                    try:
                                        owner_block = container.find_element(By.CLASS_NAME, "CDe7pd")
                                    except:
                                        owner_block = None
                                    found_texts = []
                                    for elem in container.find_elements(By.XPATH, ".//*"):
                                        try:
                                            # Skip anything within the owner reply block
                                            if owner_block and owner_block in elem.find_elements(By.XPATH, "./ancestor-or-self::*"):
                                                continue
                                            class_attr = elem.get_attribute("class") or ""
                                            elem_text = elem.text.strip()
                                            if elem_text:
                                                found_texts.append(elem_text)
                                        except:
                                            continue
                                    # After building found_texts, ensure reviews with only owner responses are skipped
                                    if not found_texts:
                                        text = ""
                                    else:
                                        text = " ".join(found_texts)
                                        source = "structural"

                                        # Filter out structurally captured junk: reviewer names, icons, timestamps, UI tags
                                        cleaned_text = re.sub(r"[^a-zA-Z0-9\s.,!?']", "", text)
                                        word_count = len(cleaned_text.split())
                                        lowercase_ratio = sum(c.islower() for c in cleaned_text) / (len(cleaned_text) + 1)

                                        # Explicit junk triggers
                                        junk_keywords = ["", "", "New", "Updated", "stars", "reviews"]
                                        junk_detected = any(kw in text for kw in junk_keywords)

                                        if word_count < 5 or lowercase_ratio < 0.05 or junk_detected:
                                            text = ""
                                except:
                                    pass
                            # Fallback #4: narrowest known container using jslog="127691"
                            if not text:
                                try:
                                    review_subtree = card.find_element(By.XPATH, './/div[@jslog="127691"]')
                                    targeted_spans = review_subtree.find_elements(By.CLASS_NAME, 'RfDO5c')
                                    extracted = [
                                        s.text.strip() for s in targeted_spans
                                        if s.text.strip() and "RfDO5c" not in (s.get_attribute("class") or "")
                                    ]
                                    if extracted:
                                        text = " ".join(extracted)
                                        source = "jslog127691"
                                except:
                                    pass
                    if debug_mode:
                        with open("debug_review_html_output.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n--- Review #{i+1} ---\n")
                            f.write(f"Used fallback: {source}\n")
                            f.write(f"Captured text:\n{text}\n")
                            f.write("-" * 80 + "\n")
                except:
                    text = ""
                    source = "none"
            except:
                text = ""
                source = "none"
            date = card.find_element(By.CLASS_NAME, 'rsqaWe').text

            review_id = card.get_attribute("data-review-id")
            numeric_rating = int(re.search(r'\d', rating).group())
            parsed_date = parse_relative_date(date)
            if not parsed_date and debug_mode:
                with open("debug_review_html_output.txt", "a", encoding="utf-8") as f:
                    f.write(f"[Missing Parsed Date] Review {review_id} → Raw date: {date}\n")

            image_elements = card.find_elements(By.XPATH, './/div[contains(@class, "KtCyie")]/button[contains(@style, "background-image")]')
            image_files = []

            for idx, img_el in enumerate(image_elements):
                try:
                    style_attr = img_el.get_attribute("style")
                    img_url = ""
                    if "background-image" in style_attr:
                        if debug_mode:
                            with open("debug_review_html_output.txt", "a", encoding="utf-8") as f:
                                f.write(f"[Image style attr] Review {review_id} → {style_attr}\n")

                        # Try matching both quoted and unquoted forms
                        match = re.search(r'url\(["\']?(https[^"\')]+)["\']?\)', style_attr)
                        if match:
                            img_url = match.group(1)
                    if img_url and "googleusercontent" in img_url:
                        image_filename = f"img_{i+1:03d}_{idx+1}.jpg"
                        image_path = os.path.join("exports", "google", "images", image_filename)
                        os.makedirs(os.path.dirname(image_path), exist_ok=True)
                        urllib.request.urlretrieve(img_url, image_path)
                        if debug_mode:
                            with open("debug_review_html_output.txt", "a", encoding="utf-8") as f:
                                f.write(f"[Image captured] Review {review_id} → {img_url}\n")
                        image_files.append(image_filename)
                except Exception:
                    continue

            # Extract like count (updated logic)
            like_count = 0
            try:
                like_span = card.find_element(By.CLASS_NAME, "pkWtMe")
                like_text = like_span.text.strip()
                if like_text.isdigit():
                    like_count = int(like_text)
            except:
                pass  # No like count means 0

            # Extract structured tags: Services, Positive tags, Negative tags, Price tags
            services = []
            positive_tags = []
            negative_tags = []
            price_tags = []

            try:
                tag_blocks = card.find_elements(By.CLASS_NAME, 'RfDO5c')
                current_label = ""
                for tag in tag_blocks:
                    tag_text = tag.text.strip()
                    if tag_text.lower() in ["services", "positive", "negative", "price"]:
                        current_label = tag_text.lower()
                        continue
                    elif current_label == "services":
                        services.append(tag_text)
                    elif current_label == "positive":
                        positive_tags.append(tag_text)
                    elif current_label == "negative":
                        negative_tags.append(tag_text)
                    elif current_label == "price":
                        price_tags.append(tag_text)
                    else:
                        if debug_mode:
                            with open("debug_review_html_output.txt", "a", encoding="utf-8") as f:
                                f.write(f"[Unrecognized tag under label '{current_label or 'none'}']: {tag_text}\n")
            except:
                pass

            data.append({
                "ReviewUID": f"R{len(data)+1:03d}",
                "Reviewer": reviewer,
                "Rating": rating,
                "RatingValue": numeric_rating,
                "DateRaw": date,
                "DateParsed": parsed_date,
                "DateParseSuccess": bool(parsed_date),
                "Review": clean_final_text(text),
                "ImageCount": len(image_files),
                "ImageFiles": ", ".join(image_files),
                "LikeCount": like_count,
                "Services": ", ".join(services),
                "PositiveTags": ", ".join(positive_tags),
                "NegativeTags": ", ".join(negative_tags),
                "PriceTags": ", ".join(price_tags)
            })

        # Export to CSV and provide download options
        if data:
            df = pd.DataFrame(data)
            # Show preview of first 3 reviews
            st.subheader("🔍 Preview of First 3 Reviews")
            # Automatic export block
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("exports", "google")
            os.makedirs(output_dir, exist_ok=True)
            filename = f"google_reviews_{timestamp}.csv"
            filepath = os.path.join(output_dir, filename)
            df.to_csv(filepath, index=False)
            st.success(f"✅ Exported automatically to: {filepath}")
        else:
            st.warning("No review data available for export.")

        # Close browser for now
        driver.quit()


if __name__ == "__main__":
    main()