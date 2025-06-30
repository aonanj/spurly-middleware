from datetime import datetime, timezone, timedelta
import random
from flask import Blueprint, jsonify
import os
from datetime import datetime, timezone
import requests
from infrastructure.clients import get_firestore_db
from infrastructure.logger import get_logger
from trendspy import Trends  

diagnostic_bp = Blueprint("diagnostic", __name__)

logger = get_logger(__name__)

def get_all_trending_topics():
    
    refresh_if_stale()
    
    try:
        db = get_firestore_db()
        doc = db.collection("trending_topics").document("weekly_pool").get()

        if not doc.exists:
            return jsonify({"status": "error", "message": "No topic pool found"}), 404

        data = doc.to_dict()
        topics = data.get("topics", [])
        last_updated = data.get("last_updated", "unknown")

        return jsonify({
            "status": "ok",
            "topic_count": len(topics),
            "last_updated": last_updated,
            "topics": topics
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# NewsAPI setup
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
CATEGORIES = ["entertainment", "technology", "sports", "general"]

def is_safe_topic(text):
    banned_words = ['murder', 'trump', 'biden', 'death', 'war', 'scandal', 'suicide', 'shooting']
    return not any(word in text.lower() for word in banned_words)


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

def get_random_trending_topic():
    try:
        db = get_firestore_db()
        doc = db.collection("trending_topics").document("weekly_pool").get()
        if not doc.exists:
            return None
        topics = doc.to_dict().get("topics", [])
        if not topics:
            return None
        return random.choice(topics).get("topic")
    except Exception as e:
        print(f"[WARN] Failed to fetch trending topic: {e}")
        return None

def refresh_if_stale():
    db = get_firestore_db()
    doc_ref = db.collection("trending_topics").document("weekly_pool")
    doc = doc_ref.get()

    should_refresh = False

    if not doc.exists:
        should_refresh = True
    else:
        data = doc.to_dict()
        last_updated_str = data.get("last_updated")
        if not last_updated_str:
            should_refresh = True
        else:
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
                now = datetime.now(timezone.utc)
                if (now - last_updated) >= timedelta(days=10):
                    should_refresh = True
            except Exception:
                should_refresh = True

    if should_refresh:
        all_topics = get_google_trends() + get_newsapi_topics(CATEGORIES, limit_per=10)
        filtered = [t for t in all_topics if is_safe_topic(t["topic"])]
        doc_ref.set({
            "topics": filtered,
            "last_updated": datetime.now(timezone.utc).isoformat()
        })
        print(f"Refreshed {len(filtered)} topics.")
        return True
    else:
        print("Trending topics are up to date.")
        return False
