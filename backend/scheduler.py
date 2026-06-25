import threading
import time
import requests
import datetime
from croniter import croniter
from database import (
    load_due_scheduled_tasks,
    update_scheduled_task_run,
    deactivate_scheduled_task,
    save_message,
    load_messages,
    get_connection,
    get_secret,
    USE_SQLITE
)
from .ai_service import generate_chat_response
from .schemas import ChatRequest

_scheduler_thread = None
_stop_event = threading.Event()

def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Scheduler Telegram send error: {e}")

def send_whatsapp_message(access_token: str, phone_number_id: str, to_number: str, text: str):
    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text
        }
    }
    try:
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Scheduler WhatsApp send error: {e}")

def get_user_details(user_id: int) -> dict | None:
    try:
        with get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            cursor.close()
            return row
    except Exception as e:
        print(f"Scheduler failed to get user details: {e}")
        return None

def execute_scheduled_task(task: dict):
    task_id = task["id"]
    user_id = task["user_id"]
    conversation_id = task["conversation_id"]
    prompt = task["prompt"]
    task_name = task["task_name"]
    cron_expr = task["cron_expression"]
    interval = task["interval_seconds"]
    
    now = datetime.datetime.now()
    
    # 1. Calculate next runtime
    next_run_at = None
    if cron_expr:
        try:
            iter = croniter(cron_expr, now)
            next_run_at = iter.get_next(datetime.datetime)
        except Exception as e:
            print(f"Cron parse error on task {task_id}: {e}")
            deactivate_scheduled_task(task_id)
            return
    elif interval:
        next_run_at = now + datetime.timedelta(seconds=interval)
        
    if next_run_at:
        update_scheduled_task_run(task_id, next_run_at, now)
    else:
        deactivate_scheduled_task(task_id)
        
    # 2. Run the AI task
    print(f"Executing scheduled task {task_id} ({task_name}) for user {user_id}")
    
    # Save the trigger message in database as a user message
    if conversation_id:
        save_message(conversation_id, "user", f"[Scheduled Task: {task_name}] {prompt}")
        
    # Fetch chat history for context
    messages_history = []
    if conversation_id:
        db_msgs = load_messages(conversation_id)
        if db_msgs:
            for m in db_msgs[:-1]:
                messages_history.append({
                    "role": m.get("role"),
                    "content": m.get("content")
                })
                
    # Build ChatRequest
    chat_req = ChatRequest(
        prompt=prompt,
        provider="Gemini",
        conversation_id=conversation_id,
        messages=messages_history,
        document_text="",
        data_context="",
        image_base64=None,
        image_mime=None,
        web_search=False
    )
    
    try:
        ai_resp = generate_chat_response(chat_req)
        answer = ai_resp.answer
    except Exception as e:
        answer = f"Error executing scheduled task: {str(e)}"
        
    # 3. Save assistant reply in database
    if conversation_id:
        save_message(conversation_id, "assistant", answer)
        
    # 4. Forward notification/message to Telegram or WhatsApp if user is a bot user
    user_info = get_user_details(user_id)
    if user_info:
        username = user_info.get("username", "")
        if username.startswith("telegram_"):
            chat_id = username.split("_")[1]
            token = get_secret("TELEGRAM_BOT_TOKEN", "")
            if token and token != "your-telegram-bot-token":
                msg_text = f"🔔 **Scheduled Task: {task_name}**\n\n{answer}"
                send_telegram_message(token, chat_id, msg_text)
        elif username.startswith("whatsapp_"):
            to_number = username.split("_")[1]
            access_token = get_secret("WHATSAPP_ACCESS_TOKEN", "")
            phone_id = get_secret("WHATSAPP_PHONE_NUMBER_ID", "")
            if access_token and phone_id and access_token != "your-whatsapp-access-token":
                msg_text = f"🔔 Scheduled Task: {task_name}\n\n{answer}"
                send_whatsapp_message(access_token, phone_id, to_number, msg_text)

def scheduler_loop():
    print("Background Task Scheduler thread started successfully.")
    while not _stop_event.is_set():
        try:
            due_tasks = load_due_scheduled_tasks()
            for task in due_tasks:
                t = threading.Thread(target=execute_scheduled_task, args=(task,))
                t.daemon = True
                t.start()
        except Exception as e:
            print(f"Error in scheduler loop tick: {e}")
        time.sleep(30)

def start_scheduler():
    global _scheduler_thread, _stop_event
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=scheduler_loop, name="BackgroundAIScheduler")
    _scheduler_thread.daemon = True
    _scheduler_thread.start()

def stop_scheduler():
    global _stop_event
    _stop_event.set()
    print("Background Task Scheduler stop request sent.")
