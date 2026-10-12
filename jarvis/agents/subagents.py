import asyncio
import urllib.parse
from jarvis.actions.browser import BrowserManager

class ResearchSubAgent:
    """Specialized background agent that crawls and gathers information."""
    
    @staticmethod
    async def research_topic(topic: str) -> dict:
        # Opens research tab for user and returns briefing summary
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
