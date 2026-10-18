#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Reminder Engine — 智能提醒执行引擎
负责实际执行JSON读写、时间解析、提醒触发判断、异常处理
"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

# 配置路径
REMINDER_DIR = Path.home() / ".workbuddy" / "smart-reminder"
PENDING_FILE = REMINDER_DIR / "pending.json"
HISTORY_FILE = REMINDER_DIR / "history.json"

# 确保目录存在
def _ensure_dirs():
    REMINDER_DIR.mkdir(parents=True, exist_ok=True)
    if not PENDING_FILE.exists():
        with open(PENDING_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)
    if not HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False)

# 读取pending.json  
def _load_pending():
    _ensure_dirs()
    try:
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

# 保存pending.json
def _save_pending(data):
    _ensure_dirs()
    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 读取history.json
def _load_history():
    _ensure_dirs()
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

# 保存history.json
def _save_history(data):
    _ensure_dirs()
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 时间解析：把"明天"、"3天后"等转为ISO日期
def _parse_time(time_raw):
    today = datetime.now()
    
    # 已经是ISO日期格式
    if re.match(r'^\d{4}-\d{2}-\d{2}$', time_raw):
        return time_raw
    
    # "今天"
    if "今天" in time_raw or "今日" in time_raw or "今" == time_raw.strip():
        return today.strftime('%Y-%m-%d')
    
    # "明天"
    if "明天" in time_raw or "明日" in time_raw:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # "后天"
    if "后天" in time_raw:
        return (today + timedelta(days=2)).strftime('%Y-%m-%d')
    
    # "X天后"、"X天之后"
    m = re.search(r'(\d+)\s*天[后之]', time_raw)
    if m:
        days = int(m.group(1))
        return (today + timedelta(days=days)).strftime('%Y-%m-%d')
    
    # "下周X"
    weekdays = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    m = re.search(r'下周([一二三四五六日天])', time_raw)
    if m:
        target_wd = weekdays.get(m.group(1))
        if target_wd is not None:
            days_ahead = target_wd - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
    
    # "X月X号"、"X月X日"
    m = re.search(r'(\d{1,2})月(\d{1,2})[号日]', time_raw)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        # 如果日期已过，算明年
        try:
            parsed = datetime(year, month, day)
            if parsed.date() < today.date():
                parsed = datetime(year + 1, month, day)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            pass
    
    # "X号"、"X日"（默认当月）
    m = re.search(r'(\d{1,2})[号日]$', time_raw)
    if m:
        day = int(m.group(1))
        month = today.month
        try:
            parsed = datetime(today.year, month, day)
            if parsed.date() < today.date():
                month += 1
                if month > 12:
                    month = 1
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            pass
    
    # 解析失败，返回None
    return None

# 生成提醒ID
def _gen_id():
    now = datetime.now()
    return f"rem_{now.strftime('%Y%m%d_%H%M%S')}_{now.microsecond // 1000:03d}"

# ===== 命令实现 =====

# detect：检测用户输入是否含提醒请求
def cmd_detect(user_input):
    time_words = ["今天", "明天", "后天", "下周", "后天", "后天", 
                  "提醒", "记得", "别忘了", "通知我", "到时候",
                  "天后", "号", "日"]
    action_words = ["提醒", "记得", "别忘了", "通知", "告诉我", "叫我"]
    
    has_time = any(w in user_input for w in time_words)
    has_action = any(w in user_input for w in action_words)
    
    # 待办语义检测
    todo_words = ["要去", "得去", "需要", "准备", "计划", "安排"]
    has_todo = any(w in user_input for w in todo_words)
    
    reminders = []
    
    if has_time and (has_action or has_todo or "提醒" in user_input or "记得" in user_input):
        # 尝试提取时间和内容
        # 简单提取：找"提醒/记得"后面的内容
        for trigger in ["提醒我", "记得", "别忘了", "通知我", "叫我"]:
            if trigger in user_input:
                idx = user_input.index(trigger) + len(trigger)
                rest = user_input[idx:].strip()
                # 去掉开头的"要"、"去"等
                rest = re.sub(r'^[要去吧啦呢]+', '', rest).strip()
                if rest:
                    # 提取时间
                    time_raw = ""
                    for tw in time_words:
                        if tw in user_input:
                            # 找时间词附近的内容
                            m = re.search(r'(今天|明天|后天|下周[一二三四五六日天]|\d+天后|\d+月\d+号|\d+号|\d+日)', user_input)
                            if m:
                                time_raw = m.group(1)
                            break
                    reminders.append({
                        "time_raw": time_raw if time_raw else user_input[:10],
                        "action": rest[:100]  # 限制长度
                    })
                    break
    
    return {"has_reminder": len(reminders) > 0, "reminders": reminders}

# add：写入新提醒
def cmd_add(time_raw, action):
    parsed_date = _parse_time(time_raw)
    reminder = {
        "id": _gen_id(),
        "time_raw": time_raw,
        "time_parsed": parsed_date,
        "action": action[:200],  # 限制长度
        "created_at": datetime.now().isoformat(),
        "status": "pending"
    }
    pending = _load_pending()
    pending.append(reminder)
    _save_pending(pending)
    return {"success": True, "id": reminder["id"]}

# check：检查是否有到期提醒
def cmd_check():
    today = datetime.now().strftime('%Y-%m-%d')
    pending = _load_pending()
    due = []
    
    for r in pending:
        if r.get("status") != "pending":
            continue
        parsed = r.get("time_parsed")
        if parsed is None:
            # 无法解析时间的，只要创建了就认为到期
            due.append(r)
        elif parsed <= today:
            due.append(r)
    
    # 按创建时间排序，最早的先提醒
    due.sort(key=lambda x: x.get("created_at", ""))
    return {"due": due}

# done：标记提醒已处理
def cmd_done(reminder_id):
    pending = _load_pending()
    history = _load_history()
    found = None
    
    for i, r in enumerate(pending):
        if r.get("id") == reminder_id:
            found = pending.pop(i)
            break
    
    if found:
        found["status"] = "done"
        found["triggered_at"] = datetime.now().isoformat()
        history.append(found)
        _save_pending(pending)
        _save_history(history)
        return {"success": True}
    
    return {"success": False, "error": "reminder_id not found"}

# list：列出所有待处理提醒
def cmd_list():
    pending = _load_pending()
    pending = [r for r in pending if r.get("status") == "pending"]
    pending.sort(key=lambda x: x.get("created_at", ""))
    return {"pending": pending}

# remove：删除提醒
def cmd_remove(reminder_id):
    return cmd_done(reminder_id)  # 逻辑相同：从pending移到history

# ===== CLI入口 =====
def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少命令参数"}, ensure_ascii=False))
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    try:
        if cmd == "detect":
            user_input = sys.argv[2] if len(sys.argv) > 2 else ""
            result = cmd_detect(user_input)
            print(json.dumps(result, ensure_ascii=False))
        
        elif cmd == "add":
            if len(sys.argv) < 4:
                print(json.dumps({"error": "add需要时间和内容参数"}, ensure_ascii=False))
                sys.exit(1)
            time_raw = sys.argv[2]
            action = sys.argv[3]
            result = cmd_add(time_raw, action)
            print(json.dumps(result, ensure_ascii=False))
        
        elif cmd == "check":
            result = cmd_check()
            print(json.dumps(result, ensure_ascii=False))
        
        elif cmd == "done":
            if len(sys.argv) < 3:
                print(json.dumps({"error": "done需要提醒ID"}, ensure_ascii=False))
                sys.exit(1)
            reminder_id = sys.argv[2]
            result = cmd_done(reminder_id)
            print(json.dumps(result, ensure_ascii=False))
        
        elif cmd == "list":
            result = cmd_list()
            print(json.dumps(result, ensure_ascii=False))
        
        elif cmd == "remove":
            if len(sys.argv) < 3:
                print(json.dumps({"error": "remove需要提醒ID"}, ensure_ascii=False))
                sys.exit(1)
            reminder_id = sys.argv[2]
            result = cmd_remove(reminder_id)
            print(json.dumps(result, ensure_ascii=False))
        
        else:
            print(json.dumps({"error": f"未知命令: {cmd}"}, ensure_ascii=False))
            sys.exit(1)
    
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
