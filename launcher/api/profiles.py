import time
from ..storage import load_json, save_json
from ..config import PROFILES_FILE


def handle_list():
    return load_json(PROFILES_FILE)


def handle_create(data):
    profiles = load_json(PROFILES_FILE)
    profile = data
    if not profile.get("id"):
        profile["id"] = f"profile_{int(time.time() * 1000)}"
    profiles = [p for p in profiles if p.get("id") != profile["id"]]
    profiles.append(profile)
    save_json(PROFILES_FILE, profiles)
    return profile


def handle_delete(profile_id):
    profiles = load_json(PROFILES_FILE)
    profiles = [p for p in profiles if p.get("id") != profile_id]
    save_json(PROFILES_FILE, profiles)
    return {"ok": True}
