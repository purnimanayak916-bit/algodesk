"""
social.py
Social trading layer for AlgoDesk — groups, signal sharing, social feed.
Uses st.session_state for demo/sandbox data (same as paper_trader.py).
No real money, no real broker execution — demo mode only.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib


def init_social_state():
    """Initialize social trading session state."""
    defaults = {
        "social_groups": {},        # group_id -> {name, password_hash, owner, members: [usernames], created_at}
        "social_signals": [],       # list of signal dicts
        "social_responses": [],      # list of response dicts
        "social_username": None,     # current user's display name
        "social_feed": [],           # activity feed items
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def ensure_username():
    """Get or set the current user's social username."""
    if not st.session_state.get("social_username"):
        st.session_state["social_username"] = f"Trader_{datetime.now().strftime('%H%M%S')}"
    return st.session_state["social_username"]


def create_group(name: str, password: str, username: str) -> dict:
    """Create a new trading group."""
    group_id = f"grp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(st.session_state['social_groups'])}"
    st.session_state["social_groups"][group_id] = {
        "name": name,
        "password_hash": hash_password(password),
        "owner": username,
        "members": [username],
        "created_at": datetime.now(),
        "capital_allocation": 10000,
        "max_loss_limit": 500,
    }
    add_feed_item(f"🏠 Group '{name}' created by {username}")
    return {"group_id": group_id, "name": name}


def join_group(group_id: str, password: str, username: str) -> dict:
    """Join an existing group."""
    groups = st.session_state["social_groups"]
    if group_id not in groups:
        return {"success": False, "message": "Group not found"}
    
    group = groups[group_id]
    if not check_password(password, group["password_hash"]):
        return {"success": False, "message": "Wrong password"}
    
    if username in group["members"]:
        return {"success": False, "message": "Already a member"}
    
    group["members"].append(username)
    add_feed_item(f"👋 {username} joined group '{group['name']}'")
    return {"success": True, "message": f"Joined '{group['name']}'"}


def get_my_groups(username: str) -> list:
    """Get all groups the user is a member of."""
    result = []
    for gid, g in st.session_state["social_groups"].items():
        if username in g["members"]:
            result.append({
                "group_id": gid,
                "name": g["name"],
                "owner": g["owner"],
                "members": g["members"],
                "member_count": len(g["members"]),
                "capital_allocation": g.get("capital_allocation", 10000),
                "max_loss_limit": g.get("max_loss_limit", 500),
                "created_at": g["created_at"],
            })
    return result


def update_risk_settings(group_id: str, username: str, capital: float, max_loss: float) -> bool:
    """Update the user's risk settings for a group."""
    groups = st.session_state["social_groups"]
    if group_id not in groups:
        return False
    if username not in groups[group_id]["members"]:
        return False
    groups[group_id]["capital_allocation"] = capital
    groups[group_id]["max_loss_limit"] = max_loss
    return True


def post_signal(group_id: str, symbol: str, direction: str, analysis: str,
                username: str, rsi: float = None, price: float = None) -> dict:
    """Post an AI signal to a group."""
    groups = st.session_state["social_groups"]
    if group_id not in groups:
        return {"success": False, "message": "Group not found"}
    if username not in groups[group_id]["members"]:
        return {"success": False, "message": "Not a member"}
    
    signal = {
        "id": len(st.session_state["social_signals"]) + 1,
        "group_id": group_id,
        "group_name": groups[group_id]["name"],
        "symbol": symbol,
        "direction": direction,
        "analysis": analysis,
        "posted_by": username,
        "rsi": rsi,
        "price": price,
        "created_at": datetime.now(),
        "responses": {},
    }
    st.session_state["social_signals"].append(signal)
    add_feed_item(f"📡 {username} posted {direction} signal for {symbol} in '{groups[group_id]['name']}'")
    return {"success": True, "signal_id": signal["id"]}


def get_group_signals(group_id: str) -> list:
    """Get all signals for a group."""
    return [s for s in st.session_state["social_signals"] if s["group_id"] == group_id]


def respond_to_signal(signal_id: int, response: str, username: str, paper_trader) -> dict:
    """Respond yes/no to a signal. Yes creates a demo trade."""
    signals = st.session_state["social_signals"]
    signal = next((s for s in signals if s["id"] == signal_id), None)
    if not signal:
        return {"success": False, "message": "Signal not found"}
    
    groups = st.session_state["social_groups"]
    group = groups.get(signal["group_id"])
    if not group or username not in group["members"]:
        return {"success": False, "message": "Not a member of this group"}
    
    # Record the response
    signal["responses"][username] = response
    
    demo_trade_result = None
    if response == "yes":
        capital = group.get("capital_allocation", 10000)
        price = signal.get("price") or 100.0
        qty = int(capital / price) if price > 0 else 10
        
        if signal["direction"] == "BUY":
            ok, msg = paper_trader.buy(signal["symbol"], qty, price, f"Social signal by {signal['posted_by']}")
        else:
            ok, msg = (True, "OK")  # For SELL signals in demo, we just note the response
        
        if ok:
            demo_trade_result = {"qty": qty, "price": price, "status": "executed"}
            add_feed_item(f"✅ {username} said YES to {signal['symbol']} {signal['direction']} (demo trade created)")
        else:
            demo_trade_result = {"status": "failed", "reason": msg}
    else:
        add_feed_item(f"❌ {username} said NO to {signal['symbol']} {signal['direction']}")
    
    st.session_state["social_responses"].append({
        "signal_id": signal_id,
        "username": username,
        "response": response,
        "demo_trade": demo_trade_result,
        "created_at": datetime.now(),
    })
    
    return {"success": True, "demo_trade": demo_trade_result}


def get_social_feed(limit: int = 20) -> list:
    """Get recent social activity feed."""
    return st.session_state.get("social_feed", [])[-limit:][::-1]


def add_feed_item(text: str):
    """Add an item to the social feed."""
    st.session_state["social_feed"].append({
        "text": text,
        "time": datetime.now(),
    })


def get_signal_stats(group_id: str = None) -> dict:
    """Get stats about signals."""
    signals = st.session_state["social_signals"]
    if group_id:
        signals = [s for s in signals if s["group_id"] == group_id]
    
    buy_count = sum(1 for s in signals if s["direction"] == "BUY")
    sell_count = sum(1 for s in signals if s["direction"] == "SELL")
    yes_count = sum(1 for s in signals for r in s.get("responses", {}).values() if r == "yes")
    no_count = sum(1 for s in signals for r in s.get("responses", {}).values() if r == "no")
    
    return {
        "total_signals": len(signals),
        "buy_signals": buy_count,
        "sell_signals": sell_count,
        "yes_responses": yes_count,
        "no_responses": no_count,
    }
