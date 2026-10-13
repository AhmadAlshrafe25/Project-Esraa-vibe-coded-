import asyncio
import urllib.parse
import urllib.request
import re
import html
from typing import Dict, Any, List
import aiohttp
from jarvis.actions.browser import BrowserManager

class ResearchSubAgent:
    """Autonomous Deep Web Research Agent (100% Free, Zero External API Keys Required)."""

    @staticmethod
    def _clean_html(raw_html: str) -> str:
        """Strips scripts, styles, tags and unescapes entities."""
        # Strip script and style blocks
        clean = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", " ", clean)
        # Unescape HTML entities
        clean = html.unescape(clean)
        # Collapse whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def search_web_free(query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Scrapes DuckDuckGo HTML for organic search results and snippets."""
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        req = urllib.request.Request(url, headers=headers)
        results = []

        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                page = resp.read().decode("utf-8", errors="ignore")

            titles = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.DOTALL)
            snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', page, re.DOTALL)

            for i in range(min(len(titles), len(snippets), max_results)):
                raw_href, raw_title = titles[i]
                clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_href).query)
                clean_url = parsed_qs.get("uddg", [raw_href])[0]
                clean_snip = html.unescape(re.sub(r"<[^>]+>", "", snippets[i])).strip()

                if clean_title and clean_snip:
                    results.append({
                        "title": clean_title,
                        "url": clean_url,
                        "snippet": clean_snip
                    })
        except Exception as e:
            # Fallback to Wikipedia search API
            try:
                wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote_plus(query)}&format=json"
                req_w = urllib.request.Request(wiki_url, headers=headers)
                with urllib.request.urlopen(req_w, timeout=5) as w_resp:
                    import json
                    w_data = json.loads(w_resp.read().decode("utf-8", errors="ignore"))
                    for item in w_data.get("query", {}).get("search", [])[:max_results]:
                        clean_title = item.get("title", "")
                        clean_snip = html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", "")))
                        results.append({
                            "title": clean_title,
                            "url": f"https://en.wikipedia.org/wiki/{urllib.parse.quote_plus(clean_title)}",
                            "snippet": clean_snip
                        })
            except Exception:
                pass

        return results

    @classmethod
    async def deep_research(cls, query: str) -> Dict[str, Any]:
        """
        Runs autonomous deep research:
        1. Gathers multi-source web snippets without paid search APIs.
        2. Synthesizes findings using Gemini / Groq / Ollama or smart extraction.
        3. Returns concise, structured executive intelligence briefing.
        """
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, cls.search_web_free, query, 4)

        if not results:
            return {
                "status": "warning",
                "topic": query,
                "summary": f"I was unable to retrieve live web data for '{query}', sir.",
                "sources": []
            }

        sources = [r["url"] for r in results if "url" in r]
        compiled_text = "\n".join([f"Source [{r['title']}]: {r['snippet']}" for r in results])

        # Attempt to synthesize via LLM for a crisp, high-density briefing
        summary = ""
        try:
            from jarvis.brain.engine import brain_service
            prompt = (
                f"You are Ezra, an AI intelligence analyst. Synthesize these research findings into a crisp, "
                f"2-sentence executive briefing for the user on topic '{query}'. Focus on facts and conclusions:\n\n{compiled_text}"
            )
            llm_res = await brain_service._call_gemini(f"Synthesize research for: {query}", prompt)
            if llm_res and llm_res.get("speech_text"):
                summary = llm_res["speech_text"]
        except Exception:
            pass

        if not summary:
            # Fallback to direct top findings
            top_snippets = " ".join([r["snippet"] for r in results[:2]])
            summary = f"Research briefing on {query}: {top_snippets[:240]}..."

        return {
            "status": "success",
            "topic": query,
            "summary": summary,
            "sources": sources,
            "findings": results
        }

    @staticmethod
    async def research_topic(topic: str) -> dict:
        """Legacy helper for backward compatibility."""
        encoded = urllib.parse.quote_plus(topic)
        BrowserManager.open_url(f"https://en.wikipedia.org/wiki/Special:Search?search={encoded}")
        return {
            "status": "completed",
            "topic": topic,
            "summary": f"Dispatched research agent on '{topic}'. Opened reference documentation in browser."
        }

class AutomationSubAgent:
    """Background agent for timed tasks and repetitive checks."""
    
    @staticmethod
    async def schedule_reminder(seconds: int, note: str, callback_coro=None):
        await asyncio.sleep(seconds)
        if callback_coro:
            await callback_coro(note)
        return {"status": "reminded", "note": note}
