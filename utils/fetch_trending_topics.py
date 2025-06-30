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
            # Handle different possible return formats from trendspy
            if isinstance(trends_data, list):
                # If it returns a list of strings
                for i, trend in enumerate(trends_data[:limit]):
                    results.append({
                        "topic": trend,
                        "source": "GoogleTrends"
                    })
            elif isinstance(trends_data, dict):
                # If it returns a dictionary with trends
                trends_list = trends_data.get('trends', [])
                for i, trend in enumerate(trends_list[:limit]):
                    # Extract the topic name depending on the structure
                    if isinstance(trend, dict):
                        topic_name = trend.get('title', trend.get('topic', str(trend)))
                    else:
                        topic_name = str(trend)
                    
                    results.append({
                        "topic": topic_name,
                        "source": "GoogleTrends"
                    })
            else:
                # If it's a pandas DataFrame or other format
                # Convert to list and process
                try:
                    import pandas as pd
                    if isinstance(trends_data, pd.DataFrame):
                        for i, row in trends_data.head(limit).iterrows():
                            results.append({
                                "topic": str(row[0]) if len(row) > 0 else str(row),
                                "source": "GoogleTrends"
                            })
                except ImportError:
                    # If pandas is not available, try to convert to string
                    logger.warning("Unexpected data format from trendspy, attempting string conversion")
                    
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
