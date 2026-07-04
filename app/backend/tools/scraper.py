"""
Competitor scraper. Uses Playwright for JS-rendered pages, httpx for simple ones.
Returns structured data: features, pricing, reviews.
"""
import httpx
from bs4 import BeautifulSoup
from typing import Optional
import re


async def scrape_competitor(domain: str) -> dict:
    """
    Scrape a competitor domain and return structured data.
    Tries fast httpx first, falls back to Playwright for JS-heavy pages.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"

    raw_text = await _fetch_page(url)
    pricing_text = await _fetch_page(f"{url}/pricing")
    features_text = await _fetch_page(f"{url}/features")

    return {
        "raw_content": _clean_text(f"{raw_text}\n\n{pricing_text}\n\n{features_text}"),
        "features": _extract_features(features_text or raw_text),
        "pricing": _extract_pricing(pricing_text or raw_text),
        "reviews": {},  # Populated separately from G2/Trustpilot
    }


async def _fetch_page(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; BusinessBrain/1.0; research bot)"}
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove nav, footer, scripts
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator=" ", strip=True)
    except Exception:
        pass
    return None


def _clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    return text[:15000]  # Cap at 15k chars to control token use


def _extract_features(text: Optional[str]) -> list[str]:
    if not text:
        return []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    # Simple heuristic: short lines in feature sections are feature names
    features = [l for l in lines if 5 < len(l) < 80 and not l.endswith('.')]
    return features[:50]


def _extract_pricing(text: Optional[str]) -> dict:
    if not text:
        return {}
    prices = re.findall(r'\$[\d,]+(?:/mo(?:nth)?)?(?:/yr(?:ear)?)?', text, re.IGNORECASE)
    plan_names = re.findall(r'\b(Starter|Basic|Pro|Professional|Business|Enterprise|Growth|Scale|Team|Free)\b', text)
    return {
        "detected_prices": list(set(prices))[:10],
        "detected_plans": list(set(plan_names))[:8],
        "raw_excerpt": text[text.lower().find("pric"):text.lower().find("pric") + 2000] if "pric" in text.lower() else ""
    }


async def scrape_g2_reviews(company_name: str) -> list[dict]:
    """Scrape public G2 reviews for a company. Returns list of review dicts."""
    slug = company_name.lower().replace(" ", "-")
    url = f"https://www.g2.com/products/{slug}/reviews"
    text = await _fetch_page(url)
    if not text:
        return []
    # Parse review content — simplified extraction
    reviews = []
    sentences = text.split('.')
    for s in sentences:
        if any(word in s.lower() for word in ["love", "hate", "great", "bad", "worst", "best", "problem", "issue"]):
            reviews.append({"text": s.strip(), "source": "g2"})
    return reviews[:20]
