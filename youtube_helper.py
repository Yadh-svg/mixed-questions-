"""
YouTube Helper Module
Provides utilities:
1. get_searchable_query  — uses Gemini to convert a question into a concise YouTube search query
2. search_youtube_videos — queries YouTube Data API v3 and returns a list of candidate videos
3. pick_best_video       — uses Gemini to evaluate candidates and select the best educational video
4. fetch_yt_videos_for_question — orchestrates the 3 steps above
"""

import streamlit as st
from google import genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import re

BLOCKED_CHANNEL_IDS = set()
BLOCKED_CHANNEL_NAMES = set()

def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)

def is_blocked_channel(channel_id: str, channel_title: str) -> bool:
    if channel_id in BLOCKED_CHANNEL_IDS:
        return True
    if any(blocked in channel_title.lower() for blocked in BLOCKED_CHANNEL_NAMES):
        return True
    return False

def get_searchable_query(question_text: str, grade: str = "") -> str:
    """Uses Gemini 2.5 Flash Lite to generate a strict, optimized YouTube search query."""
    client = get_gemini_client()
    if not client:
        # Fallback to plain stripping
        plain = re.sub(r"[#*_`\[\]()]", "", question_text).strip()
        return plain[:120]
        
    try:
        grade_rule = f'- You MUST append the exact grade level to the end of the query this is the grade level of this question : {grade}. Do not omit this.'
        prompt = f"""You are an expert at creating YouTube search queries for educational math/science videos.

Analyze the following educational content and extract the core concept:

{question_text}

Generate a YouTube search query to find the BEST teaching video for this concept.

STRICT RULES:
- 5 to 8 words maximum
- Always include the subject area (math, geometry, science, etc.)
{grade_rule}
- Use curriculum/textbook language a teacher would use
- The query MUST reflect the academic concept, not a visual/art interpretation
- NO words like: MCQ, exam, solution, answer, quiz, worksheet, test, case study, problem
- NO punctuation or special characters
- NO explanation, NO quotes, NO labels — output the search query ONLY

OUTPUT: One search query, nothing else."""

        # with open("youtube_prompt_debug.txt", "w", encoding="utf-8") as f:
        #     f.write(prompt)

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        plain = re.sub(r"[#*_`\[\]()]", "", question_text).strip()
        return plain[:120]


def search_youtube_videos(query: str, max_results: int = 10) -> dict:
    """Queries YouTube Data API and returns full details for candidates."""
    try:
        api_key = st.secrets.get("YOUTUBE_API_KEY", "")
        if not api_key:
            return {"status": "error", "message": "YouTube API key not configured.", "data": []}

        youtube = build("youtube", "v3", developerKey=api_key)

        search_results = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=max_results,
            relevanceLanguage="en",
            safeSearch="strict",
            videoEmbeddable="true",
            order="relevance",
            regionCode="US",
        ).execute()

        video_ids = [
            item["id"]["videoId"]
            for item in search_results.get("items", [])
            if not is_blocked_channel(
                item["snippet"]["channelId"],
                item["snippet"]["channelTitle"]
            )
        ]

        if not video_ids:
            return {"status": "success", "data": []}

        videos_data = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids)
        ).execute()

        results = []
        for item in videos_data.get("items", []):
            stats   = item.get("statistics", {})
            details = item.get("contentDetails", {})
            snippet = item["snippet"]

            results.append({
                "title":       snippet["title"],
                "channel":     snippet["channelTitle"],
                "video_id":    item["id"],
                "url":         f"https://www.youtube.com/watch?v={item['id']}",
                "description": snippet.get("description", ""),
                "views":       int(stats.get("viewCount", 0)),
                "likes":       int(stats.get("likeCount", 0)),
                "duration":    details.get("duration", ""),
                "tags":        snippet.get("tags", []),
            })

        return {"status": "success", "data": results}

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


def pick_best_videos(candidates: list[dict], topic_context: str) -> list[dict]:
    """Uses Gemini to pick up to 3 best videos from the candidates, or none if irrelevant."""
    if not candidates:
        return []
        
    client = get_gemini_client()
    if not client:
        # Fallback to the first 3
        return candidates[:3]
        
    try:
        candidates_str = "\n".join([
            f"{i+1}. Title: {r['title']}\n"
            f"   Channel: {r['channel']}\n"
            f"   Views: {r['views']:,} | Likes: {r['likes']:,}\n"
            f"   Duration: {r['duration']}\n"
            f"   Description: {r['description'][:200]}\n"
            f"   Tags: {', '.join(r['tags'][:10])}\n"
            for i, r in enumerate(candidates)
        ])

        prompt = f"""You are helping pick the best YouTube video to explain a concept to a student.

TOPIC BEING TAUGHT:
{topic_context[:1000]}

CANDIDATE VIDEOS:
{candidates_str}

TASK: Pick up to 3 video numbers that best teach this concept to a student. If none of the videos are relevant to the topic being taught, explicitly reject them.

CRITERIA:
- Title and description must match the academic concept
- Must look like an actual lesson or tutorial
- Prefer higher view counts as a quality signal
- Avoid art, photography, filmmaking, or unrelated content
- Avoid Shorts (duration PT30S, PT59S etc.)

OUTPUT: 
- If videos are relevant, reply ONLY with a comma-separated list of the best video numbers (e.g. "3, 1, 5" or "4, 2" or "1"). Order them from best to worst.
- If NO videos are relevant to the specific topic, reply EXACTLY with the word "NONE"."""

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        
        text_resp = response.text.strip().upper()
        
        if "NONE" in text_resp:
            return []
            
        # Parse the numbers strictly
        best_indices = []
        for match in re.finditer(r'\d+', text_resp):
            idx = int(match.group()) - 1
            if 0 <= idx < len(candidates) and idx not in best_indices:
                best_indices.append(idx)
                if len(best_indices) == 3:
                    break
                    
        if best_indices:
            return [candidates[i] for i in best_indices]
        return candidates[:3]
        
    except Exception as e:
        print(f"Error in pick_best_videos: {e}")
        return candidates[:3]


def fetch_yt_videos_for_question(question_text: str, grade: str = "", max_results: int = 10) -> tuple:
    """
    Orchestrates the YouTube fetch:
    1. Generates search query via Gemini.
    2. Searches YouTube for 10 candidates.
    3. Re-ranks with Gemini to pick the top 3 best videos (or none if irrelevant).
    Returns (query, status_dict) where status_dict contains the accepted best videos.
    """
    search_query = get_searchable_query(question_text, grade=grade)
    
    # 2. Get candidates
    yt_result = search_youtube_videos(search_query, max_results=max_results)
    
    if yt_result["status"] == "success" and yt_result["data"]:
        candidates = yt_result["data"]
        
        # 3. Pick best videos
        best_videos = pick_best_videos(candidates, question_text)
        
        # Reformat dict to match original expected output list of {title, url}
        if best_videos:
            yt_result["data"] = [{"title": v["title"], "url": v["url"]} for v in best_videos]
        else:
            yt_result["data"] = []
            
    return search_query, yt_result
