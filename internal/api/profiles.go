package api

import (
	"fmt"
	"log/slog"
	"strings"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

// ProfileCreate creates a profile, or replaces an existing one in place
// (never appended at the end, which would undo drag-to-reorder).
func (a *API) ProfileCreate(data *ordjson.OMap) *ordjson.OMap {
	var result *ordjson.OMap
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			slog.Error("Cannot load profiles", "err", err)
			profiles = nil
		}
		profile := data
		if ordjson.GetStr(profile, "id") == "" {
			profile.Set("id", fmt.Sprintf("profile_%d", time.Now().UnixMilli()))
		}
		var existingIdx = -1
		for i, p := range profiles {
			if ordjson.GetStr(p, "id") == ordjson.GetStr(profile, "id") {
				existingIdx = i
				break
			}
		}
		var before *ordjson.OMap
		if existingIdx >= 0 {
			before = profiles[existingIdx].Clone()
			profiles[existingIdx] = profile
		} else {
			profiles = append(profiles, profile)
		}
		a.DB.Save(store.ColProfiles, profiles)
		action := "updated"
		details := (*ordjson.OMap)(nil)
		if before == nil {
			action = "created"
		} else {
			details = ordjson.New().Set("changed", ordjsonArr(store.ChangedFields(before, profile)))
		}
		a.DB.RecordAudit(action, "profile", ordjson.GetStr(profile, "id"),
			ordjson.GetStr(profile, "name"), before, profile.Clone(), details)
		result = profile
	})
	return result
}

// ProfileDelete moves a profile to the trash (group = "__trash__").
func (a *API) ProfileDelete(profileID string) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			return
		}
		for _, p := range profiles {
			if ordjson.GetStr(p, "id") != profileID {
				continue
			}
			before := p.Clone()
			p.Set("group", "__trash__")
			a.DB.Save(store.ColProfiles, profiles)
			a.DB.RecordAudit("deleted", "profile", profileID,
				ordjson.GetStr(p, "name"), before, p.Clone(), nil)
			return
		}
	})
	return ok
}

// ProfileRestore pulls a profile out of the trash.
func (a *API) ProfileRestore(profileID string) (*ordjson.OMap, bool) {
	var restored *ordjson.OMap
	found := false
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			return
		}
		for _, p := range profiles {
			if ordjson.GetStr(p, "id") != profileID || ordjson.GetStr(p, "group") != "__trash__" {
				continue
			}
			before := p.Clone()
			p.Set("group", "")
			a.DB.Save(store.ColProfiles, profiles)
			a.DB.RecordAudit("restored", "profile", profileID,
				ordjson.GetStr(p, "name"), before, p.Clone(), nil)
			restored = p
			found = true
			return
		}
	})
	return restored, found
}

// ProfilePermanentDelete removes a profile for good, deleting its
// schedules with it and recording the cascade in the audit entry.
func (a *API) ProfilePermanentDelete(profileID string) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			return
		}
		var target *ordjson.OMap
		remaining := make([]*ordjson.OMap, 0, len(profiles))
		for _, p := range profiles {
			if ordjson.GetStr(p, "id") == profileID {
				target = p
			} else {
				remaining = append(remaining, p)
			}
		}
		if err := a.DB.Save(store.ColProfiles, remaining); err != nil {
			slog.Error("Cannot save profiles", "err", err)
			remaining = nil
		}
		if target != nil {
			var removedSchedules []any
			a.DB.WithCollection(store.ColSchedules, func() {
				schedules, err := a.DB.Load(store.ColSchedules)
				if err != nil {
					return
				}
				for _, s := range schedules {
					if ordjson.GetStr(s, "target_id") == profileID {
						removedSchedules = append(removedSchedules, s.Get("id"))
					}
				}
				if len(removedSchedules) > 0 {
					kept := schedules[:0]
					for _, s := range schedules {
						if ordjson.GetStr(s, "target_id") != profileID {
							kept = append(kept, s)
						}
					}
					a.DB.Save(store.ColSchedules, kept)
				}
			})
			details := (*ordjson.OMap)(nil)
			if len(removedSchedules) > 0 {
				details = ordjson.New().Set("schedules_removed", removedSchedules)
			}
			a.DB.RecordAudit("permanently_deleted", "profile", profileID,
				ordjson.GetStr(target, "name"), target.Clone(), nil, details)
		}
		_ = remaining
	})
	return ok
}

// ProfileDuplicate copies a profile right after its position in the
// list, with a unique " (copy)" name.
func (a *API) ProfileDuplicate(profileID string) (*ordjson.OMap, bool) {
	var dup *ordjson.OMap
	found := false
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			return
		}
		index := -1
		for i, p := range profiles {
			if ordjson.GetStr(p, "id") == profileID {
				index = i
				break
			}
		}
		if index < 0 {
			return
		}
		source := profiles[index]
		existingNames := map[string]bool{}
		for _, p := range profiles {
			existingNames[ordjson.GetStr(p, "name")] = true
		}
		duplicate := source.Clone()
		duplicate.Set("id", "profile_"+randHex12())
		base := orDefaultStr(ordjson.GetStr(source, "name"), "Profile")
		name := base + " (copy)"
		for n := 2; existingNames[name]; n++ {
			name = fmt.Sprintf("%s (copy %d)", base, n)
		}
		duplicate.Set("name", name)
		profiles = append(profiles, nil)
		copy(profiles[index+2:], profiles[index+1:])
		profiles[index+1] = duplicate
		a.DB.Save(store.ColProfiles, profiles)
		a.DB.RecordAudit("created", "profile", ordjson.GetStr(duplicate, "id"),
			ordjson.GetStr(duplicate, "name"), nil, duplicate.Clone(),
			ordjson.New().Set("duplicate_of", ordjson.GetStr(source, "name")))
		dup = duplicate
		found = true
	})
	return dup, found
}

// ProfileReorder applies a new id order and audits the change when it
// actually differs.
func (a *API) ProfileReorder(data *ordjson.OMap) *ordjson.OMap {
	ok := ordjson.New().Set("ok", true)
	order := ordjson.GetArr(data, "order")
	a.DB.WithCollection(store.ColProfiles, func() {
		profiles, err := a.DB.Load(store.ColProfiles)
		if err != nil {
			return
		}
		byID := map[string]*ordjson.OMap{}
		for _, p := range profiles {
			byID[ordjson.GetStr(p, "id")] = p
		}
		ordered := make([]*ordjson.OMap, 0, len(order))
		orderedSet := map[string]bool{}
		for _, raw := range order {
			id, _ := raw.(string)
			if p, ok := byID[id]; ok && !orderedSet[id] {
				ordered = append(ordered, p)
				orderedSet[id] = true
			}
		}
		for _, p := range profiles {
			if !orderedSet[ordjson.GetStr(p, "id")] {
				ordered = append(ordered, p)
			}
		}
		previous := make([]string, len(profiles))
		current := make([]string, len(ordered))
		for i, p := range profiles {
			previous[i] = ordjson.GetStr(p, "id")
		}
		for i, p := range ordered {
			current[i] = ordjson.GetStr(p, "id")
		}
		a.DB.Save(store.ColProfiles, ordered)
		if joinStrings(current, ",") != joinStrings(previous, ",") {
			orderAny := make([]any, len(current))
			for i, id := range current {
				orderAny[i] = id
			}
			a.DB.RecordAudit("reordered", "profiles", "", "Profile order", nil, nil,
				ordjson.New().Set("order", orderAny))
		}
	})
	return ok
}

func ordjsonArr(list []string) []any {
	out := make([]any, len(list))
	for i, s := range list {
		out[i] = s
	}
	return out
}

func randHex12() string {
	return store.NewID()[:12]
}

func orDefaultStr(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

func joinStrings(parts []string, sep string) string {
	return strings.Join(parts, sep)
}
