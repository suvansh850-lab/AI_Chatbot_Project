import urllib.request
import urllib.parse
from bs4 import BeautifulSoup

def perform_ddg_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Performs a search on DuckDuckGo HTML search and returns a list of result dictionaries."""
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read()
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for a in soup.find_all("a", class_="result__snippet"):
            parent = a.find_parent("div", class_="result__body")
            if not parent:
                continue
            title_el = parent.find("a", class_="result__url")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el["href"]
            
            # Decode DuckDuckGo redirect link
            parsed = urllib.parse.urlparse(link)
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                actual_url = qs["uddg"][0]
            else:
                if link.startswith("//"):
                    link = "https:" + link
                actual_url = link
                
            snippet = a.get_text(strip=True)
            results.append({"title": title, "link": actual_url, "snippet": snippet})
            if len(results) >= max_results:
                break
        return results
    except Exception:
        # Return empty list on failure
        return []

def format_search_results_context(results: list[dict[str, str]], query: str) -> str:
    """Formats list of search results into a clean context block for LLMs."""
    if not results:
        return ""
    
    context_lines = [f"[Web Search Results for: \"{query}\"]"]
    for idx, r in enumerate(results, 1):
        context_lines.append(f"{idx}. Title: {r['title']}\n   Source: {r['link']}\n   Snippet: {r['snippet']}")
    
    return "\n\n".join(context_lines)
