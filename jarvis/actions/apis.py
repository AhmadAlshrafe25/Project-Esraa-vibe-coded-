import os
import json
import subprocess
import requests
from typing import Dict, Any, List
from config.settings import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

class ApiManager:
    """Connects external REST APIs to provide Ezra with real-time world intelligence, market data, weather, news, and developer tools."""

    @staticmethod
    def get_weather(city: str = "") -> Dict[str, Any]:
        """Fetches live weather, temperature, humidity, and condition for any city (or auto-detects current location)."""
        try:
            city_query = city.strip() if city else ""
            url = f"https://wttr.in/{city_query}?format=j1"
            resp = requests.get(url, timeout=3.0, headers={"User-Agent": "ProjectEzra/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                area = data.get("nearest_area", [{}])[0]
                area_name = area.get("areaName", [{}])[0].get("value", city or "Current Location")
                country = area.get("country", [{}])[0].get("value", "")

                return {
                    "status": "success",
                    "location": f"{area_name}, {country}".strip(", "),
                    "temp_c": f"{current.get('temp_C', '--')}°C",
                    "feels_like_c": f"{current.get('FeelsLikeC', '--')}°C",
                    "condition": current.get("weatherDesc", [{}])[0].get("value", "Clear"),
                    "humidity": f"{current.get('humidity', '--')}%",
                    "wind_speed_kmph": current.get("windspeedKmph", "--"),
                    "summary": f"In {area_name}, it is currently {current.get('temp_C')}°C with {current.get('weatherDesc', [{}])[0].get('value')}. Humidity is at {current.get('humidity')}%."
                }
            return {"status": "error", "message": f"Weather service responded with status {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": f"Could not fetch weather: {e}"}

    @staticmethod
    def get_crypto_price(coins: str = "bitcoin,ethereum", currency: str = "usd") -> Dict[str, Any]:
        """Fetches real-time crypto prices and 24h change for coins like bitcoin, ethereum, solana, etc."""
        try:
            clean_coins = coins.lower().replace(" ", "")
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={clean_coins}&vs_currencies={currency.lower()}&include_24hr_change=true"
            resp = requests.get(url, timeout=3.5, headers={"User-Agent": "ProjectEzra/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                results = {}
                for coin, details in data.items():
                    price = details.get(currency.lower(), 0)
                    change = round(details.get(f"{currency.lower()}_24h_change", 0), 2)
                    results[coin] = {
                        "price": f"{price:,.2f} {currency.upper()}",
                        "change_24h": f"{change:+.2f}%"
                    }
                return {"status": "success", "currency": currency.upper(), "data": results}
            return {"status": "error", "message": f"CoinGecko API returned status {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "message": f"Could not fetch crypto prices: {e}"}

    @staticmethod
    def get_exchange_rate(base_currency: str = "USD", target_currency: str = "EUR") -> Dict[str, Any]:
        """Gets real-time fiat currency exchange rates (USD, EUR, GBP, EGP, SAR, JPY, etc.)."""
        try:
            base = base_currency.upper().strip() or "USD"
            target = target_currency.upper().strip() or "EUR"
            url = f"https://open.er-api.com/v6/latest/{base}"
            resp = requests.get(url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("rates", {})
                target_rate = rates.get(target)
                if target_rate is not None:
                    return {
                        "status": "success",
                        "base": base,
                        "target": target,
                        "rate": target_rate,
                        "summary": f"1 {base} equals {target_rate:,.4f} {target}."
                    }
                return {"status": "error", "message": f"Currency code {target} not found."}
            return {"status": "error", "message": "Failed to retrieve exchange rates."}
        except Exception as e:
            return {"status": "error", "message": f"Exchange rate error: {e}"}

    @staticmethod
    def search_wikipedia(query: str) -> Dict[str, Any]:
        """Fetches encyclopedic summary, facts, and definitions from Wikipedia REST API."""
        try:
            clean_q = query.strip().replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{clean_q}"
            resp = requests.get(url, timeout=3.5, headers={"User-Agent": "ProjectEzra/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "success",
                    "title": data.get("title", query),
                    "description": data.get("description", ""),
                    "extract": data.get("extract", "")
                }
            return {"status": "error", "message": f"No Wikipedia article found for '{query}'."}
        except Exception as e:
            return {"status": "error", "message": f"Wikipedia query error: {e}"}

    @staticmethod
    def search_instant_answer(query: str) -> Dict[str, Any]:
        """Searches DuckDuckGo Instant Answer API for quick definitions and instant facts."""
        try:
            url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
            resp = requests.get(url, timeout=3.5, headers={"User-Agent": "ProjectEzra/1.0"})
            if resp.status_code == 200:
                data = resp.json()
                abstract = data.get("AbstractText", "") or data.get("Abstract", "")
                heading = data.get("Heading", query)
                source_url = data.get("AbstractURL", "")
                if abstract:
                    return {"status": "success", "heading": heading, "answer": abstract, "source": source_url}
            # Fallback to Wikipedia search
            return ApiManager.search_wikipedia(query)
        except Exception as e:
            return {"status": "error", "message": f"DuckDuckGo search error: {e}"}

    @staticmethod
    def get_tech_news(limit: int = 5) -> Dict[str, Any]:
        """Fetches top trending tech and software stories from Hacker News."""
        try:
            top_ids_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            top_ids = requests.get(top_ids_url, timeout=3.0).json()[:limit]
            
            articles = []
            for item_id in top_ids:
                try:
                    item_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                    item = requests.get(item_url, timeout=2.0).json()
                    if item and "title" in item:
                        articles.append({
                            "title": item.get("title"),
                            "url": item.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
                            "score": item.get("score", 0)
                        })
                except Exception:
                    continue

            return {"status": "success", "articles": articles}
        except Exception as e:
            return {"status": "error", "message": f"Failed to retrieve tech news: {e}"}

    @staticmethod
    def get_network_info() -> Dict[str, Any]:
        """Retrieves public IP, local Wi-Fi SSID, and connection latency."""
        info = {}
        # 1. Public IP
        try:
            ip_resp = requests.get("https://api.ipify.org?format=json", timeout=2.5)
            if ip_resp.status_code == 200:
                info["public_ip"] = ip_resp.json().get("ip", "Unknown")
        except Exception:
            info["public_ip"] = "Offline/Unreachable"

        # 2. Local Wi-Fi SSID via nmcli
        try:
            res = subprocess.run(
                ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
                capture_output=True, text=True, timeout=2.0
            )
            for line in res.stdout.splitlines():
                if line.startswith("yes:"):
                    info["wifi_ssid"] = line.split(":", 1)[1]
                    break
            if "wifi_ssid" not in info:
                info["wifi_ssid"] = "Ethernet / Not connected to Wi-Fi"
        except Exception:
            info["wifi_ssid"] = "Unknown"

        # 3. Ping latency
        try:
            ping_res = subprocess.run(
                ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
                capture_output=True, text=True, timeout=3.0
            )
            if "time=" in ping_res.stdout:
                lat = ping_res.stdout.split("time=")[1].split()[0]
                info["ping_latency"] = f"{lat} ms"
            else:
                info["ping_latency"] = "No response"
        except Exception:
            info["ping_latency"] = "Unavailable"

        return {"status": "success", "network": info}

    @staticmethod
    def get_github_info(username: str = "AhmadAlshrafe25", repo: str = "") -> Dict[str, Any]:
        """Retrieves user profile, public repositories, or repo details from GitHub REST API."""
        try:
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ProjectEzra/1.0"}
            if GITHUB_TOKEN:
                headers["Authorization"] = f"token {GITHUB_TOKEN}"

            if repo:
                url = f"https://api.github.com/repos/{username}/{repo}"
                resp = requests.get(url, headers=headers, timeout=3.5)
                if resp.status_code == 200:
                    d = resp.json()
                    return {
                        "status": "success",
                        "repo_name": d.get("full_name"),
                        "stars": d.get("stargazers_count"),
                        "forks": d.get("forks_count"),
                        "open_issues": d.get("open_issues_count"),
                        "description": d.get("description") or "No description provided."
                    }
                return {"status": "error", "message": f"GitHub repo {username}/{repo} not found."}
            else:
                url = f"https://api.github.com/users/{username}"
                resp = requests.get(url, headers=headers, timeout=3.5)
                if resp.status_code == 200:
                    d = resp.json()
                    # Also fetch list of recent repos
                    repos_url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=5"
                    repos_resp = requests.get(repos_url, headers=headers, timeout=3.5)
                    repo_names = [r.get("name") for r in repos_resp.json()] if repos_resp.status_code == 200 else []
                    return {
                        "status": "success",
                        "username": d.get("login"),
                        "public_repos_count": d.get("public_repos"),
                        "followers": d.get("followers"),
                        "recent_repos": repo_names
                    }
                return {"status": "error", "message": f"GitHub user {username} not found."}
        except Exception as e:
            return {"status": "error", "message": f"GitHub API error: {e}"}

api_manager = ApiManager()
