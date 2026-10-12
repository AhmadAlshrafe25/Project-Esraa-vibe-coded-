import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiohttp
from config.settings import EMAIL_USER, EMAIL_APP_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class CommsManager:
    """Manages email notifications and Telegram bot messaging."""

    @staticmethod
    def send_email(to_email: str, subject: str, body: str) -> dict:
        if not EMAIL_USER or not EMAIL_APP_PASSWORD:
            return {
                "status": "warning", 
                "message": "Email credentials not configured in .env (EMAIL_USER and EMAIL_APP_PASSWORD)."
            }
        
        try:
            msg = MIMEMultipart()
            msg['From'] = f"Project Ezra <{EMAIL_USER}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
                server.sendmail(EMAIL_USER, to_email, msg.as_string())

            return {"status": "success", "message": f"Email successfully sent to {to_email}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send email: {str(e)}"}

    @staticmethod
    async def send_telegram_message(text: str, chat_id: str = None) -> dict:
        target_chat = chat_id or TELEGRAM_CHAT_ID
        if not TELEGRAM_BOT_TOKEN or not target_chat:
            return {
                "status": "warning",
                "message": "Telegram token or chat_id not set in .env."
            }

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": target_chat, "text": text, "parse_mode": "Markdown"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    res_json = await response.json()
                    if res_json.get("ok"):
                        return {"status": "success", "message": "Telegram message delivered."}
                    return {"status": "error", "message": f"Telegram API error: {res_json}"}
        except Exception as e:
            return {"status": "error", "message": f"Telegram sending error: {str(e)}"}
