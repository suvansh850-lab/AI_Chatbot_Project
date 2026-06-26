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

# (Telegram and WhatsApp notifications removed from scheduled tasks module)

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
            # Keep only the last 10 messages to avoid exceeding provider TPM limits
            recent_msgs = db_msgs[-11:-1] if len(db_msgs) > 11 else db_msgs[:-1]
            for m in recent_msgs:
                messages_history.append({
                    "role": m.get("role"),
                    "content": m.get("content")
                })
                
    # Build ChatRequest
    chat_req = ChatRequest(
        prompt=prompt,
        provider="Groq",
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
        
    # (Telegram and WhatsApp notification forwarding removed)

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
