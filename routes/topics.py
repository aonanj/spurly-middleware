from flask import Blueprint, jsonify, current_app
from datetime import datetime, timezone
import requests
from pytrends.request import TrendReq
from infrastructure.clients import get_firestore_db

diagnostic_bp = Blueprint("diagnostic", __name__)

@diagnostic_bp.route("/topics", methods=["GET"])
def get_trending_topics():
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
NEWSAPI_KEY = current_app.config.get("NEWS_API_KEY")
CATEGORIES = ["entertainment", "technology", "sports", "general"]

def is_safe_topic(text):
    banned_words = ['murder', 'trump', 'biden', 'death', 'war', 'scandal', 'suicide', 'shooting']
    return not any(word in text.lower() for word in banned_words)

def get_google_trends(limit=10):
    pytrends = TrendReq(hl='en-US', tz=360)
    df = pytrends.trending_searches(pn='united_states')
    return [{"topic": row[0], "source": "GoogleTrends"} for row in df.head(limit).values]

def get_newsapi_topics(categories, limit_per=10):
    results = []
    for cat in categories:
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "us",
            "category": cat,
            "pageSize": limit_per,
            "apiKey": NEWSAPI_KEY
        }
        r = requests.get(url, params=params)
        articles = r.json().get("articles", [])
        for a in articles:
            results.append({
                "topic": a["title"],
                "source": f"NewsAPI-{cat}"
            })
    return results

@diagnostic_bp.route("/refresh-topics", methods=["GET"])
def refresh_trending_topics():
    try:
        db = get_firestore_db()

        # Fetch and combine
        raw = get_google_trends() + get_newsapi_topics(CATEGORIES, limit_per=20)
        filtered = [t for t in raw if is_safe_topic(t["topic"])]

        # Save to Firestore
        doc_ref = db.collection("trending_topics").document("weekly_pool")
        doc_ref.set({
            "topics": filtered,
            "last_updated": datetime.utcnow().isoformat()
        })

        return jsonify({
            "status": "ok",
            "updated_count": len(filtered),
            "sources": CATEGORIES,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

