from trendspy import Trends
import requests
from datetime import datetime, timezone
import os
from infrastructure.clients import get_firestore_db
from infrastructure.logger import get_logger


db = get_firestore_db()
logger = get_logger(__name__)
    
# NewsAPI Setup
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
CATEGORIES = ["entertainment", "technology", "sports", "general"]

def get_google_trends(limit=10):
    """
    Fetches trending searches from Google Trends using trendspy with error handling.

    Args:
        limit (int): The maximum number of trends to return.

    Returns:
        list: A list of trending topics, or an empty list if an error occurs.
    """
    try:
        # Initialize trendspy
        tr = Trends()
        
        # Get trending searches for the United States
        trends_data = tr.trending_now(geo='US')
        
        # Format the results to match the expected output
        results = []
        if trends_data:
            # The trendspy library returns a list of TrendKeyword objects.
            # We need to access the .keyword attribute to get the string.
            for trend in trends_data[:limit]:
                results.append({
                    "topic": trend.keyword,  # Access the .keyword attribute here
                    "source": "GoogleTrends"
                })
                    
        return results
        
    except Exception as e:
        logger.error(f"TrendsPy request failed with an error: {e}")
        return []  # Return an empty list to prevent a crash
    
def get_newsapi_topics(categories, limit_per=10):
    results = []
    for cat in categories:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "us",
            "category": cat,
            "pageSize": limit_per,
            "apiKey": NEWS_API_KEY
        }
        r = requests.get(url, params=params)
        articles = r.json().get("articles", [])
        for a in articles:
            results.append({
                "topic": a["title"],
                "source": f"NewsAPI-{cat}"
            })
    return results

def is_safe_topic(text):
    banned_words = ['murder', 'trump', 'biden', 'death', 'war', 'scandal', 'suicide', 'shooting']
    return not any(word in text.lower() for word in banned_words)

def upload_to_firestore(topics):
    doc_ref = db.collection("trending_topics").document("weekly_pool")
    doc_ref.set({
        "topics": topics,
        "last_updated": datetime.now(timezone.utc).isoformat()
    })

def run_topic_fetcher():
    trends = get_google_trends() + get_newsapi_topics(CATEGORIES)
    filtered = [t for t in trends if is_safe_topic(t["topic"])]
    upload_to_firestore(filtered)

if __name__ == "__main__":
    run_topic_fetcher()
