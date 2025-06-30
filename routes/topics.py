from flask import Blueprint, jsonify
from datetime import datetime, timezone
from services.topic_service import get_google_trends, get_newsapi_topics, fetch_reddit_topics, is_safe_topic, get_all_trending_topics
from infrastructure.clients import get_firestore_db
from infrastructure.logger import get_logger

diagnostic_bp = Blueprint("diagnostic", __name__)

logger = get_logger(__name__)

CATEGORIES = ["entertainment", "sports", "science", "general"]

@diagnostic_bp.route("/topics", methods=["GET"])
def get_trending_topics():
    try:
        return get_all_trending_topics()

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@diagnostic_bp.route("/refresh-topics", methods=["GET"])
def refresh_trending_topics():
    try:
        db = get_firestore_db()

        # Fetch and combine
        sources = []
        google_trends = get_google_trends()
        if len(google_trends) > 0:
            sources.append("GoogleTrends")
        newsapi_trends = get_newsapi_topics(CATEGORIES, limit_per=5)
        if len(newsapi_trends) > 0:
            sources.append("NewsAPI")
        reddit_trends = fetch_reddit_topics()
        if len(reddit_trends) > 0:
            sources.append("Reddit")
        raw = google_trends + newsapi_trends + reddit_trends
        filtered = [t for t in raw if is_safe_topic(t["topic"])]

        # Save to Firestore
        doc_ref = db.collection("trending_topics").document("weekly_pool")
        doc_ref.set({
            "topics": filtered,
            "last_updated": datetime.now(timezone.utc).isoformat()
        })

        return jsonify({
            "status": "ok",
            "updated_count": len(filtered),
            "sources": sources,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500