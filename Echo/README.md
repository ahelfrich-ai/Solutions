Echo – Google Business Review Harvester (v1.7)

Echo is a streamlined Google Business review scraper designed for flexible data extraction and delivery. Built with Python, Streamlit, and Google Drive integration, Echo enables small businesses or consultants to quickly capture customer reviews and package them into shareable reports.

⸻

🚀 Key Features
	•	Scrapes visible Google Business reviews
 
	•	Extracts review text, timestamps, ratings, images, and structured tags
 
	•	Handles fallbacks for malformed or missing review text
 
	•	Exports clean CSVs with optional image ZIP packaging
 
	•	Includes business name automatically in all file outputs
 
	•	Optional Completed Reports ZIP for one-step delivery
 
	•	Uploads files directly to Google Drive for client handoff
 
	•	Streamlit interface for simple, client-friendly use
 
	•	Headless browser option for faster, non-visual scraping
 
	•	Debug log option for traceability and testing

⸻

📂 Folder Structure
echo-scraper/
├── echo_Google_Business_HTML_v1.7.py   # Main script
├── drive_uploader.py                    # Handles Google Drive uploads
├── requirements.txt                     # Required Python packages
├── README.md                            # This file
├── LICENSE                              # MIT License
├── exports/                             # Temporary images folder (auto-deleted post-run)


⸻

🛠️ Built With
	•	Python 3.11
	•	Streamlit
	•	Undetected Chromedriver (Selenium)
	•	Pandas
	•	Google API Client (Drive integration)
	•	Requests

⸻

⚙️ How It Works
	1.	Paste the Google Maps Reviews tab link into Echo’s interface.
	2.	Choose options for:
	•	Headless mode (faster scraping)
	•	Standard or Completed Reports ZIP delivery
	3.	Click Start Extraction
	4.	Echo scrapes the reviews, extracts images, and exports all data:
	•	CSV
	•	Images ZIP
	•	Debug log (optional, for fallback review trace)
	5.	All outputs are uploaded directly to Google Drive.

⸻

📈 Use Cases
	•	UX research and product feedback collection
	•	Small business review management
	•	Competitive analysis of public reviews
	•	Client report generation (via Completed Reports ZIP)

⸻

🔮 Coming in Echo v2
	•	Web-hosted SaaS version
	•	Built-in LLM analysis for summarization and insights
	•	Verifier Tool for review count consistency
	•	Deduplication across multiple runs
	•	Dashboard visualization features

⸻

📄 License

MIT License
