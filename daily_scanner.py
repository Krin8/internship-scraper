import json
import re
import datetime
import urllib.parse
from playwright.sync_api import sync_playwright

STATE_FILE = "scraper_state.json"
TRACKER_FILE = "internship_tracker.md"

def load_companies():
    companies = []
    with open(TRACKER_FILE, "r") as f:
        for line in f.readlines():
            if line.startswith("- [ ]") or line.startswith("- [x]"):
                company = line.replace("- [ ]", "").replace("- [x]", "").strip()
                company = re.sub(r' \(.*\)', '', company).strip()
                companies.append(company)
    return companies

def run_scraper():
    companies = load_companies()
    
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
        
    start_idx = state.get("current_index", 0)
    batch_size = state.get("batch_size", 35)
    
    if start_idx >= len(companies):
        start_idx = 0  # Loop back if we've reached the end
        
    end_idx = min(start_idx + batch_size, len(companies))
    target_companies = companies[start_idx:end_idx]
    
    print(f"Processing companies {start_idx} to {end_idx}...")
    
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        for company in target_companies:
            print(f"Scraping: {company}")
            try:
                # Use Playwright to search DuckDuckGo directly (bypasses most API rate limits)
                search_query = f"{company} careers \"intern\" OR \"internship\" India"
                search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
                
                page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                
                links = page.locator("a.result__url")
                if links.count() == 0:
                    results.append({"company": company, "status": "No career page found", "url": "N/A"})
                    continue
                    
                url = links.first.get_attribute("href")
                if not url.startswith("http"):
                    url = "https://" + url.lstrip("/")
                
                # Navigate to the found URL
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # Wait a bit for JS to render
                page.wait_for_timeout(2000)
                
                # Extract text safely
                body_text = page.locator("body").inner_text().lower()
                
                # Simple keyword heuristic
                found_intern = "intern" in body_text or "trainee" in body_text or "summer analyst" in body_text
                
                results.append({
                    "company": company,
                    "status": "Potential Openings Found" if found_intern else "No immediate intern keywords detected",
                    "url": url
                })
                
            except Exception as e:
                print(f"Error scraping {company}: {e}")
                results.append({"company": company, "status": f"Scrape timeout/error", "url": url if 'url' in locals() else "N/A"})
                
        browser.close()
        
    # Write the report
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    report_file = "daily_report.md"
    
    with open(report_file, "w") as f:
        f.write(f"# Daily Internship Scan Report ({date_str})\n\n")
        f.write(f"Scanned {len(target_companies)} companies (Batch {start_idx} to {end_idx}).\n\n")
        f.write("| Company | Status | Direct Career URL |\n")
        f.write("|---------|--------|-------------------|\n")
        for res in results:
            f.write(f"| {res['company']} | {res['status']} | [Link]({res['url']}) |\n")
            
    # Update state
    state["current_index"] = end_idx
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
        
    print(f"Scan complete. Report generated at {report_file}")

if __name__ == "__main__":
    run_scraper()
