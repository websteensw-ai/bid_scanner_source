from typing import Any, Dict, List, Optional

from auth import user_client

TABLE = "bid_scanner_reports"


def save_report(
    access_token: str,
    user_id: str,
    url: str,
    days: int,
    min_score: int,
    business_profile: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> None:
    client = user_client(access_token)
    client.table(TABLE).insert({
        "user_id": user_id,
        "url": url,
        "days": days,
        "min_score": min_score,
        "business_profile": business_profile,
        "results": results,
        "result_count": len(results),
    }).execute()


def list_reports(access_token: str) -> List[Dict[str, Any]]:
    client = user_client(access_token)
    res = (
        client.table(TABLE)
        .select("id, url, days, min_score, result_count, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data or []


def get_report(access_token: str, report_id: str) -> Optional[Dict[str, Any]]:
    client = user_client(access_token)
    res = client.table(TABLE).select("*").eq("id", report_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None
