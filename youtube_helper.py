"""
YouTube Helper Module
Provides two utilities:
1. get_searchable_query  — uses SarvamAI to convert a question into a concise YouTube search query
2. search_youtube_videos — queries YouTube Data API v3 and returns a list of {title, url} dicts
"""

import streamlit as st


def get_searchable_query(question_text: str, grade: str = "") -> str:
    """
    Use SarvamAI to convert a raw question (Markdown) into a concise,
    searchable sentence suitable for a YouTube search.

    Args:
        question_text: The full question text / markdown content.
        grade: Optional grade level (e.g. "Grade 8") to tailor the search query.

    Returns:
        A short, clean search query string.
    """
    try:
        from sarvamai import SarvamAI

        api_key = st.secrets.get("SARVAM_API_KEY", "")
        if not api_key:
            # Fallback: use first 120 chars of the raw text stripped of markdown
            import re
            plain = re.sub(r"[#*_`\[\]()]", "", question_text).strip()
            return plain[:120]

        client = SarvamAI(api_subscription_key=api_key)

        response = client.chat.completions(
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are given an exam question. Extract only the core mathematical concept being tested. "
                        "Generate a YouTube search query (maximum 10 words) that a student would type to learn this concept. "
                        "Focus on: topic name + specific operation or formula involved. "
                        + (f"The student is in {grade}, so you need to mention the grade also in the output as well ENGLISH Video Solution")
                        + "Ignore: question type, difficulty level, DOK, MCQ, case study, or any exam metadata. "
                        "Return ONLY the search query, nothing else.\n\n"
                        f"Question:\n{question_text[:800]}"
                    ),
                }
            ],
            temperature=0.3,
            top_p=1,
            max_tokens=60,
        )

        # Extract text from response
        if hasattr(response, "choices") and response.choices:
            return response.choices[0].message.content.strip()
        elif hasattr(response, "text"):
            return response.text.strip()
        else:
            # Try dict-style access
            resp_dict = response if isinstance(response, dict) else vars(response)
            choices = resp_dict.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
        # Fallback
        import re
        plain = re.sub(r"[#*_`\[\]()]", "", question_text).strip()
        return plain[:120]

    except Exception as e:
        # Graceful fallback: strip markdown and truncate
        import re
        plain = re.sub(r"[#*_`\[\]()]", "", question_text).strip()
        return plain[:120]


def search_youtube_videos(query: str, max_results: int = 3) -> dict:
    """
    Search YouTube for a given query using the YouTube Data API v3.

    Returns a status dict:
        {"status": "success",     "data": [{"title": str, "url": str}, ...]}
        {"status": "quota_limit", "message": str, "data": []}
        {"status": "error",       "message": str, "data": []}
    """
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        import json

        api_key = st.secrets.get("YOUTUBE_API_KEY", "")
        if not api_key:
            return {"status": "error", "message": "YouTube API key not configured.", "data": []}

        youtube = build("youtube", "v3", developerKey=api_key)

        request = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=int(max_results),  # Strict int — prevents string-type API fallback
            relevanceLanguage="en",
            regionCode="US",
        )

        response = request.execute()

        results = []
        for item in response.get("items", []):
            title = item["snippet"]["title"]
            video_id = item["id"]["videoId"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            results.append({"title": title, "url": url})

        # Debug: compare what the API returned vs what we serve
        print(f"[YT DEBUG] API returned: {len(results)} items | Serving: {min(len(results), int(max_results))} (maxResults={max_results})")

        return {"status": "success", "data": results[:int(max_results)]}

    except HttpError as e:
        try:
            error_details = json.loads(e.content).get("error", {})
            reason = error_details.get("errors", [{}])[0].get("reason", "unknown")
        except Exception:
            reason = "unknown"

        if reason == "quotaExceeded":
            return {
                "status": "quota_limit",
                "message": "🚫 Daily YouTube search quota exhausted. Try again tomorrow!",
                "data": []
            }
        return {
            "status": "error",
            "message": f"YouTube API error: {reason}",
            "data": []
        }

    except Exception as e:
        return {"status": "error", "message": str(e), "data": []}


def fetch_yt_videos_for_question(question_text: str, grade: str = "", max_results: int = 3) -> tuple:
    """
    Combined helper: converts question to search query via SarvamAI (with optional
    grade context), then fetches YouTube videos.

    Args:
        question_text: The full question markdown content.
        grade: Optional grade level (e.g. "Grade 8") from the user's session.
        max_results: Number of video results to return.

    Returns:
        (search_query: str, result_dict: dict)
        result_dict has keys: status ("success"/"quota_limit"/"error"), message, data
    """
    search_query = get_searchable_query(question_text, grade=grade)
    result = search_youtube_videos(search_query, max_results=max_results)
    return search_query, result
