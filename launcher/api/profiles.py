import copy
import time
import uuid
from ..storage import load_json, save_json, record_audit, changed_fields
from ..config import COL_PROFILES


def handle_list():
    return load_json(COL_PROFILES)


def handle_create(data):
    profiles = load_json(COL_PROFILES)
    profile = data
    if not profile.get("id"):
        profile["id"] = f"profile_{int(time.time() * 1000)}"
    existing = next((p for p in profiles if p.get("id") == profile["id"]), None)
    before = copy.deepcopy(existing) if existing else None
    profiles = [p for p in profiles if p.get("id") != profile["id"]]
    profiles.append(profile)
    save_json(COL_PROFILES, profiles)
    record_audit(
        "created" if before is None else "updated",
        "profile",
        profile["id"],
        profile.get("name"),
        before=before,
        after=copy.deepcopy(profile),
        details={"changed": changed_fields(before, profile)} if before else None,
    )
    return profile


def handle_delete(profile_id):
    profiles = load_json(COL_PROFILES)
    target = next((p for p in profiles if p.get("id") == profile_id), None)
    profiles = [p for p in profiles if p.get("id") != profile_id]
    save_json(COL_PROFILES, profiles)
    if target:
        record_audit(
            "deleted",
            "profile",
            profile_id,
            target.get("name"),
            before=copy.deepcopy(target),
        )
    return {"ok": True}


def handle_duplicate(profile_id):
    profiles = load_json(COL_PROFILES)
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
    save_json(COL_PROFILES, profiles)
    record_audit(
        "created",
        "profile",
        duplicate["id"],
        duplicate.get("name"),
        after=copy.deepcopy(duplicate),
        details={"duplicate_of": source.get("name")},
    )
    return duplicate


def handle_reorder(data):
    order = data.get("order") or []
    profiles = load_json(COL_PROFILES)
    by_id = {p.get("id"): p for p in profiles}
    ordered = [by_id[i] for i in order if i in by_id]
    ordered_set = {p.get("id") for p in ordered}
    ordered += [p for p in profiles if p.get("id") not in ordered_set]
    previous = [p.get("id") for p in profiles]
    current = [p.get("id") for p in ordered]
    save_json(COL_PROFILES, ordered)
    if current != previous:
        record_audit(
            "reordered",
            "profiles",
            None,
            "Profile order",
            details={"order": current},
        )
    return {"ok": True}
