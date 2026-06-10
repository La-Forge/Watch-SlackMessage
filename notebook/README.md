# README: Slack URL Summarizer & Tagger

## Overview
This notebook is designed to automate the process of extracting, summarizing, and tagging web links shared in Slack messages. It pulls unprocessed URLs from a source Airtable, scrapes the content, processes it using a local quantized Large Language Model (Qwen2.5-7B) along with keyword-matching algorithms, and writes the enriched data into a target Airtable.

## Steps Overview
1. **Environment Setup & Model Loading:** Installs required dependencies (Transformers, Trafilatura, etc.) and initializes the 4-bit quantized Qwen LLM.
2. **Airtable Configuration:** Establishes a connection to the Airtable API, reads the configuration secrets, and maps the input/output fields.
3. **Content Extraction:** Fetches the raw HTML/PDF content from the URLs using resilient scrapers, handling timeouts and basic parsing.
4. **Summarization & Tagging:** Applies a hybrid strategy:
    - **LLM:** Generates a concise summary, title, and key bullet points from the scraped text.
    - **Keyword Matching:** Assigns standardized tags (Resource, Concept, Topic, Sub-Topic) based on predefined vocabularies.
5. **Data Synchronization:** Writes the newly processed records to the target Airtable and exports a local CSV backup for auditing.

## Secrets Configuration
To run this notebook successfully, you will need to configure your Colab Secrets (the 🔑 icon on the left panel). The required variables, specifically `AIRTABLE_PAT` and `AIRTABLE_SLACK_BASE`, can be found securely stored in **Passbolt**.

## ⚠️ Future Industrialization Considerations
If this pipeline is to be deployed in a production/industrial environment, please note the following critical limitations and required improvements:

* **Web Access Restrictions:** Many websites currently restrict automated access (e.g., bot protection, paywalls, missing permissions). Consequently, the web scraper will fail to retrieve content, leading to the pipeline prompting `"[WARN] LLM failed for..."`.
* **Legal Access Configuration:** Future iterations must consider how to legally and reliably configure access permissions (e.g., using authenticated proxies, official APIs, or specialized scraping services that handle JavaScript/Captchas ethically).
* **Preventing Database Pollution:** Currently, when the LLM or scraper fails, the system generates an `[LLM-FALLBACK]` placeholder. In an industrial setup, the code must be refactored to handle these fallbacks strictly—either by flagging them for human review or dropping them entirely—to prevent default/fallback data from polluting the Airtable database.