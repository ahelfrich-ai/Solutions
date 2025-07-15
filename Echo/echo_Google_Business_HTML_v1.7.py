#
# OFFICIAL VERSION v1.7 (Final Echo v1 Release)
# This script builds on v1.6 and introduces the following enhancements:
# - Adds automated business name inclusion in all exported filenames (CSV, images ZIP, debug log, combined ZIP)
# - Ensures debug log always uploads directly to the Debug Logs folder, regardless of pipeline path
# - Finalizes optional Completed Reports ZIP export, skipping individual uploads when selected
# - Confirms stable, polished pipeline outputs for Echo v1 completion
#
# Confirmed Capabilities:
# - Stable scraping for businesses with up to ~300 reviews (confirmed through stress testing)
# - Full image extraction (review-uploaded photos only, not profile icons)
# - Clean filtering of owner replies, blank/deleted reviews, and UI noise
# - Structured fallbacks for missing or malformed review text
# - Headless mode toggle for faster, non-visual scraping
# - Outputs polished CSV + images with accurate metadata and business name in filenames
# - Optional Completed Reports ZIP pipeline, or client-ready modular exports
# - Debug log uploads automatically to Drive for review traceability
#
# Known Limitations:
# - May stall or degrade above ~400 reviews
# - Review count comparison is currently manual (Verifier Tool pending)
# - Reviews containing videos or multiple images with a "+" button are not fully captured; current scraper only retrieves visible first image
#
# Future Expansion (Echo v2 Plans):
# - Verifier Tool to compare the CSV against live review pages for scalable accuracy checks
# - Workaround for infinite spinner/loading stall when scraping higher review counts
# - Support for expanded image sets and video reviews
# - Deduplication logic for cross-run consistency
# - LLM-based insight generation and client dashboard features
# - Web-hosted SaaS version with UX redesign
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
from drive_uploader import upload_file_to_drive
def clean_final_text(raw_text):
    if not raw_text:
        return ""
    lowered = raw_text.lower()
    if "response from the owner" in lowered:
        return ""
    return raw_text.strip()


def launch_browser(headless_mode=False):
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    if headless_mode:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    driver = uc.Chrome(options=options, use_subprocess=True)
    return driver


def main():
    st.title("Echo: Review Extraction Made Simple")
    st.markdown("""
    Paste a Google Maps link to the business’s **Reviews tab**, and Echo will extract all available customer reviews, clean the data, and prepare it for download or further analysis.
    """)
    # Add headless mode checkbox at the top
    url = st.text_input("")

    st.caption("🔗 **Tip:** Copy the link from the **Reviews tab**, not just the main business link.")
    st.markdown("---")  # Visual separator

    headless_mode = st.checkbox("Run in headless mode for faster scraping (no visible browser)", value=False)

    zip_and_send = st.checkbox("Also zip CSV + Images and send to Completed Reports folder", value=False)

    # Add "Start Extraction" button below headless toggle
    start_extraction = st.button("Start Extraction")

    from urllib.parse import urlparse, unquote

    try:
        path = urlparse(url).path
        # Extract the part after '/place/'
        business_name_raw = path.split('/place/')[1].split('/')[0]
        business_name = unquote(business_name_raw).replace('+', ' ')
    except Exception:
        business_name = "Unknown Business"

    sanitized_business_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', business_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_path = f"{sanitized_business_name}_debug_{timestamp}.txt"

    # Scraper logic runs only when the Start Extraction button is pressed
    if url and start_extraction:
        st.info("Launching browser...")
        driver = launch_browser(headless_mode)
        driver.get(url)
        # business_name is now extracted from the URL above
        # business_name = driver.find_element(By.CLASS_NAME, 'DU9Pgb').text  # Extracted from URL instead
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
        from datetime import timedelta

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
                        with open(debug_path, "a", encoding="utf-8") as f:
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
                with open(debug_path, "a", encoding="utf-8") as f:
                    f.write(f"[Missing Parsed Date] Review {review_id} → Raw date: {date}\n")

            image_elements = card.find_elements(By.XPATH, './/div[contains(@class, "KtCyie")]/button[contains(@style, "background-image")]')
            image_files = []

            for idx, img_el in enumerate(image_elements):
                try:
                    style_attr = img_el.get_attribute("style")
                    img_url = ""
                    if "background-image" in style_attr:
                        if debug_mode:
                            with open(debug_path, "a", encoding="utf-8") as f:
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
                            with open(debug_path, "a", encoding="utf-8") as f:
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
                            with open(debug_path, "a", encoding="utf-8") as f:
                                f.write(f"[Unrecognized tag under label '{current_label or 'none'}']: {tag_text}\n")
            except:
                pass

            # Check if owner responded
            owner_responded = False
            try:
                card.find_element(By.CLASS_NAME, "CDe7pd")
                owner_responded = True
            except:
                owner_responded = False

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
                "PriceTags": ", ".join(price_tags),
                "OwnerResponded": owner_responded,
                "ClientName": business_name,
            })

        # Export to CSV and provide download options
        if data:
            df = pd.DataFrame(data)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{sanitized_business_name}_reviews_{timestamp}.csv"
            df.to_csv(filename, index=False)
        else:
            st.warning("No review data available for export.")
            return  # Stop processing if no data

        # Create and upload ZIP of image files
        import zipfile

        image_folder_path = os.path.join("exports", "google", "images")
        zip_path = f"{sanitized_business_name}_images_{timestamp}.zip"

        def create_zip_from_images(image_folder_path, output_zip_path):
            with zipfile.ZipFile(output_zip_path, 'w') as zipf:
                for root, _, files in os.walk(image_folder_path):
                    for file in files:
                        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                            file_path = os.path.join(root, file)
                            arcname = file
                            zipf.write(file_path, arcname)
            return output_zip_path

        if os.path.exists(image_folder_path):
            zip_result = create_zip_from_images(image_folder_path, zip_path)
            import shutil
            shutil.rmtree(image_folder_path, ignore_errors=True)

        # Close browser for now
        driver.quit()

        # Handle ZIP and upload logic based on zip_and_send toggle
        if zip_and_send:
            combined_zip_name = f"{sanitized_business_name}_Completed_{timestamp}.zip"
            with zipfile.ZipFile(combined_zip_name, 'w') as zipf:
                if os.path.exists(filename):
                    zipf.write(filename, arcname=filename)
                    os.remove(filename)

                if os.path.exists(zip_path):
                    zipf.write(zip_path, arcname=zip_path)
                    os.remove(zip_path)

            completed_folder_id = "1zNFK4qrevy7lMTvXo3BHXckUmo0vbJ9a"
            final_zip_link = upload_file_to_drive(combined_zip_name, folder_id=completed_folder_id)
            st.write("📤 Completed ZIP uploaded to Completed Reports folder:", final_zip_link)

            os.remove(combined_zip_name)
        else:
            # Proceed with normal individual uploads if zip_and_send is not selected
            csv_link = upload_file_to_drive(filename, folder_id="1npT9OnZ8SwKTiVKRpWS2U8gxosooPTkZ")
            st.write("📤 CSV uploaded to Google Drive:", csv_link)
            os.remove(filename)

            if os.path.exists(zip_path):
                zip_link = upload_file_to_drive(zip_path, folder_id="1-GUlZL7EFxux19o__sfBax4F1snCQgdQ")
                st.write("📤 Images ZIP uploaded to Google Drive:", zip_link)
                st.caption("⚠️ Google Drive may not preview ZIP files correctly. Download to view contents.")
                os.remove(zip_path)

        # Always upload debug file to Debug Logs folder, regardless of ZIP export toggle
        debug_folder_id = "1EtBEoQoCeAGzMo9KQD_pkHJoBhBTnXbm"
        if os.path.exists(debug_path):
            debug_link = upload_file_to_drive(debug_path, folder_id=debug_folder_id)
            st.write("📤 Debug log uploaded to Debug Logs folder:", debug_link)
            os.remove(debug_path)


if __name__ == "__main__":
    main()
