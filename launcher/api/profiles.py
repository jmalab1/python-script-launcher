import copy
import time
import uuid
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


def handle_duplicate(profile_id):
    profiles = load_json(PROFILES_FILE)
    index = next((i for i, p in enumerate(profiles) if p.get("id") == profile_id), None)
    if index is None:
        return None
    source = profiles[index]
    existing_ids = {p.get("id") for p in profiles}
    duplicate = copy.deepcopy(source)
    duplicate["id"] = f"profile_{uuid.uuid4().hex[:12]}"
    while duplicate["id"] in existing_ids:
        duplicate["id"] = f"profile_{uuid.uuid4().hex[:12]}"
    base = source.get("name") or "Profile"
    existing_names = {p.get("name") for p in profiles}
    name = f"{base} (copy)"
    n = 2
    while name in existing_names:
        name = f"{base} (copy {n})"
        n += 1
    duplicate["name"] = name
    profiles.insert(index + 1, duplicate)
    save_json(PROFILES_FILE, profiles)
    return duplicate


def handle_reorder(data):
    order = data.get("order") or []
    profiles = load_json(PROFILES_FILE)
    by_id = {p.get("id"): p for p in profiles}
    ordered = [by_id[i] for i in order if i in by_id]
    ordered_set = {p.get("id") for p in ordered}
    ordered += [p for p in profiles if p.get("id") not in ordered_set]
    save_json(PROFILES_FILE, ordered)
    return {"ok": True}
