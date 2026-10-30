"""Cooking-only plans: derive portions and single-use take-away allocations from facts.

No recipe selection, secondary recipe store or actual leftover inventory lives here.
Unchanged Yuvomi sources may satisfy only already persisted allocations; increasing
an occupied source would exceed this operation's authorized write scope.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from .meals_api import slot
from .menu_metadata import metadata, notes_block, scale
from .planning_context import day_range, fail
from .recipe_engine import Recipes

DAY_NAMES = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def recipe_metadata(recipe):
    presented = Recipes.present(recipe)
    if "metadata_error" in presented:
        fail("invalid_metadata", "Rezeptmetadaten beschädigt; in Yuvomi klären.")
    return (presented.get("menu_metadata") or {}).get("metadata", {})


def accepts(config, recipe, ident):
    profile, meta = config["profiles"][ident], recipe_metadata(recipe)
    denied = set()
    for reference in meta.get("mag_nicht", []):
        matches = {p for p, v in config["profiles"].items() if reference in {p, v["name"]}}
        if len(matches) != 1:
            fail("profile_unclear", "mag_nicht: unbekannte/mehrdeutige Person im Rezept.")
        denied |= matches
    return recipe["id"] not in profile.get("dislikes", []) and ident not in denied


def day_settings(ctx, when):
    config = ctx["config"]
    value = dict(config["week"][str(date.fromisoformat(when).weekday())])
    for override in ctx["args"].get("overrides", []):
        if override["date"] == when:
            value.update({k: override[k] for k in ("cook", "max_minutes", "recipe_id") if k in override})
    return value


def cooking_slots(ctx):
    return {
        (str(d), ctx["config"]["meal_type"])
        for d in day_range(ctx["first"], ctx["last"])
        if d.weekday() in ctx["config"]["days"] and any(p["present"] for p in ctx["facts"][str(d)].values())
    }


def prepare_cooking(ctx, assignments, sources):
    config, facts = ctx["config"], ctx["facts"]
    recipes = {r["id"]: r for r in ctx["recipes"]}
    all_recipes = {r["id"]: r for r in ctx.get("all_recipes", ctx["recipes"])}
    chosen, existing = {}, defaultdict(list)
    for row in ctx["rows"]:
        existing[slot(row)].append(row)
    for assignment in assignments:
        key = assignment["date"], config["meal_type"]
        if key in chosen:
            fail("invalid_plan", f"assignments: doppelter Kochtag {key[0]}.")
        when = date.fromisoformat(key[0])
        if not ctx["first"] <= when <= ctx["last"] or when.weekday() not in config["days"]:
            fail("invalid_plan", f"{key[0]}: kein freigegebener Kochtag.")
        if assignment["recipe_id"] not in recipes:
            fail("recipe_unclear", "recipe_id muss aus dem tatsächlichen Kontext stammen.")
        if (
            assignment.get("kind", "cook") == "reheat"
            or "source_date" in assignment
            or "extra_servings" in assignment
        ):
            fail(
                "invalid_plan",
                "Nur Kochtage zuweisen; Aufwärmquellen über reheat_sources wählen, Mengen berechnet das Backend.",
            )
        if len(existing[key]) > 1:
            fail("occupied_unclear", "Mehrere vorhandene Einträge im Zielslot; keine pauschale Ersetzung.")
        if ctx["args"]["action"] in {"create_period", "suggest_period", "create_day"} and existing[key]:
            fail("occupied", "Vorhandenen Kochtag bei Erstplanung auslassen.")
        chosen[key] = assignment
    if ctx["args"]["action"] in {"create_period", "suggest_period"}:
        if not (cooking_slots(ctx) - {key for key, rows in existing.items() if rows}) <= set(chosen):
            fail("incomplete_plan", "Alle freien Kochtage mit Frischbedarf gemeinsam zuweisen.")
    elif len(chosen) != 1:
        fail("invalid_plan", "Tagesplanung benötigt genau einen Kochtag.")

    # Persistent source claims remain authoritative and guard targeted replacements.
    claims, retained = {}, defaultdict(list)
    for key, rows in existing.items():
        for row in rows:
            block = metadata(row.get("notes"))
            if not block:
                continue
            if block.get("kind") == "reheat":
                source = block.get("source_date"), block.get("source_meal_type", key[1])
                if source in chosen:
                    fail(
                        "dependent_meal",
                        "Bestehender RC3-Aufwärmeintrag hängt von diesem Kochtag ab; zuerst ausdrücklich klären.",
                    )
            for extra in block.get("extras", []):
                try:
                    target = extra["date"], extra.get("meal_type", key[1]), extra["profile_id"]
                    date.fromisoformat(target[0])
                    if target in claims or len(rows) != 1 or Decimal(str(extra["servings"])) <= 0:
                        raise ValueError
                except (KeyError, TypeError, ValueError):
                    fail("invalid_metadata", "Zusatzportion in Yuvomi beschädigt oder mehrfach vergeben.")
                claims[target] = key
                if key in chosen:
                    retained[key].append(extra)

    selections = {}
    for source in sources:
        target = source["date"], config["meal_type"], source["profile_id"]
        if target in selections:
            fail("invalid_plan", "reheat_sources: Bedarf mehrfach zugeordnet.")
        selections[target] = source["source_date"], config["meal_type"]

    allocated, handled, ambiguous = defaultdict(list), set(), []
    end = ctx["last"] + timedelta(days=2)
    for when, people in facts.items():
        target_date = date.fromisoformat(when)
        if not ctx["first"] <= target_date <= end or target_date.weekday() not in config["days"]:
            continue
        settings = day_settings(ctx, when)
        for ident, person in people.items():
            if not person["reheat"]:
                continue
            target = when, config["meal_type"], ident
            possible = []
            for source, assignment in chosen.items():
                rec = recipes[assignment["recipe_id"]]
                age = (target_date - date.fromisoformat(source[0])).days
                if (
                    1 <= age <= settings["max_age"]
                    and recipe_metadata(rec).get("wiederaufwärmbar") is True
                    and accepts(config, rec, ident)
                ):
                    possible.append(source)
            prior = claims.get(target)
            # Future demand with no connection to this operation is outside its scope.
            in_scope = (
                target_date <= ctx["last"]
                or prior in chosen
                or (
                    ctx["args"]["action"] not in {"create_period", "suggest_period"}
                    and any(
                        1 <= (target_date - date.fromisoformat(source[0])).days <= settings["max_age"]
                        for source in chosen
                    )
                )
            )
            if not in_scope:
                continue
            handled.add(target)
            preferred = selections.get(target, prior)
            if prior is not None and preferred != prior:
                fail("dependent_meal", "Vorhandene Zusatzportion nicht still einer anderen Quelle zuordnen.")
            if prior is not None and prior not in chosen:
                row = existing[prior][0]
                block = metadata(row.get("notes"))
                rec = all_recipes.get(block.get("recipe_id"))
                extra = next(
                    e
                    for e in block["extras"]
                    if (e["date"], e.get("meal_type", prior[1]), e["profile_id"]) == target
                )
                age = (target_date - date.fromisoformat(prior[0])).days
                if (
                    not rec
                    or recipe_metadata(rec).get("wiederaufwärmbar") is not True
                    or not accepts(config, rec, ident)
                    or not 1 <= age <= settings["max_age"]
                    or Decimal(str(extra["servings"])) != Decimal(str(person["portion"]))
                ):
                    fail("dependent_meal", "Vorhandene Zusatzportion passt nicht mehr zum aktuellen Bedarf.")
                continue
            if preferred is not None:
                if preferred not in possible:
                    fail(
                        "reheat_source_invalid",
                        f"{when}/{ident}: gewählte Kochquelle ist nicht geeignet oder nicht im Schreibumfang.",
                    )
                source = preferred
            elif len(possible) != 1:
                ambiguous.append(
                    {"need": {"date": when, "profile_id": ident}, "source_dates": [p[0] for p in possible]}
                )
                continue
            else:
                source = possible[0]
            allocated[source].append(
                {
                    "date": when,
                    "meal_type": config["meal_type"],
                    "profile_id": ident,
                    "servings": person["portion"],
                }
            )
    if ambiguous:
        fail(
            "reheat_source_unclear",
            "Aufwärmbedarf benötigt akzeptierte, ausdrücklich wiederaufwärmbare Quellen innerhalb des Alterslimits. Alle offenen Entscheidungen stehen in choices. Bei mehreren Quellen reheat_sources angeben; bei keiner Rezeptwahl/Schreibumfang klären.",
            field="reheat_sources",
            **ambiguous[0],
            choices=ambiguous,
        )
    if set(selections) - handled:
        fail("invalid_plan", "reheat_sources enthält keinen tatsächlichen Bedarf dieses Vorgangs.")
    for source, extras in retained.items():
        if any((e["date"], e.get("meal_type", source[1]), e["profile_id"]) not in handled for e in extras):
            fail(
                "dependent_meal", "Bestehende Zusatzportion würde entfernt; Abhängigkeit ausdrücklich klären."
            )

    bodies, used = [], set()
    previous = set(ctx["public"]["previous_recipe_ids"])
    exceptions = set(config["repeat_exceptions"])
    used |= {
        r["recipe_id"]
        for r in ctx["rows"]
        if r.get("recipe_id")
        and slot(r) not in chosen
        and ctx["period_start"] <= date.fromisoformat(r["date"]) <= ctx["period_end"]
    }
    for key, assignment in sorted(chosen.items()):
        rec = recipes[assignment["recipe_id"]]
        meta, settings = recipe_metadata(rec), day_settings(ctx, key[0])
        requested = ctx["args"].get("requested_recipe") or settings.get("recipe_id")
        if settings.get("recipe_id") and settings["recipe_id"] != rec["id"]:
            fail("recipe_unclear", "Ausdrücklichen Rezeptwunsch für diesen Tag unverändert übernehmen.")
        if not requested:
            if rec["id"] in (used | previous) - exceptions:
                fail("repeat_forbidden", "Rezept bereits in dieser oder unmittelbar vorheriger Periode.")
            for ident, person in facts[key[0]].items():
                if person["present"] and not accepts(config, rec, ident):
                    fail("disliked_recipe", "Rezept wird von einer frisch essenden Person nicht akzeptiert.")
            elapsed, limit = meta.get("zubereitungszeit_min"), settings["max_minutes"]
            if limit is not None and (elapsed is None or elapsed > limit):
                fail(
                    "time_limit",
                    f"{key[0]}: gesamte Koch-/Gar-/Wartezeit überschreitet Tageslimit oder ist unbekannt.",
                )
            weekday = date.fromisoformat(key[0]).weekday()
            if config["rest_day"] == weekday and rec["id"] != config["rest_recipe_id"]:
                fail("invalid_plan", "Fester Restentag benötigt das konfigurierte Rezept.")
        kind = assignment.get("kind", "rest" if rec["id"] == config["rest_recipe_id"] else "cook")
        if kind == "rest" and (
            rec["id"] != config["rest_recipe_id"]
            or date.fromisoformat(key[0]).weekday() in config["rest_excluded_days"]
        ):
            fail("invalid_plan", "Resten-Rezept/Tag nicht freigegeben.")
        if kind == "emergency" and rec["id"] not in config["emergency_recipe_ids"]:
            fail("invalid_plan", "Kein konfiguriertes Notfallmenü.")
        used.add(rec["id"])
        fresh = sum((Decimal(str(p["portion"])) for p in facts[key[0]].values() if p["present"]), Decimal(0))
        extras = allocated[key]
        total = fresh + sum((Decimal(str(e["servings"])) for e in extras), Decimal(0))
        if total <= 0:
            fail(
                "attendance_unclear",
                f"{key[0]}: Kochtag benötigt Frischbedarf oder tatsächlich zugeordnete Zusatzportionen.",
            )
        factor = total / Decimal(str(meta.get("basisportionen", 4)))
        old = existing[key][0] if existing[key] else None
        cook = settings["cook"]
        explicit_cook = any(o["date"] == key[0] and "cook" in o for o in ctx["args"].get("overrides", []))
        preserving_cook = old is not None and not explicit_cook
        cook_id = (
            old.get("cook_user_id")
            if preserving_cook
            else config["profiles"][cook].get("user_id")
            if cook
            else None
        )
        if (cook_id is not None and (type(cook_id) is not int or cook_id not in ctx["members"])) or (
            not preserving_cook and cook and cook_id is None
        ):
            fail("cook_unclear", f"{key[0]}: Kochperson mit tatsächlichem Yuvomi-Mitglied verknüpfen.")
        data = {
            "v": 1,
            "mode": "cooking_only",
            "kind": kind,
            "date": key[0],
            "meal_type": key[1],
            "recipe_id": rec["id"],
            "servings_now": float(fresh),
            "servings_total": float(total),
            "scale_factor": float(factor),
            "basisportionen": meta.get("basisportionen", 4),
            "extras": extras,
        }
        details = "; ".join(
            f"{e['servings']}× {config['profiles'][e['profile_id']]['name']} für {DAY_NAMES[date.fromisoformat(e['date']).weekday()]}"
            for e in extras
        )
        summary = f"{total:g} Portionen; Faktor {factor:g}" + ("; " + details if details else "")
        suffix = f" – {total:g} Portionen" + (f" ({details})" if details else "")
        # Preserve exact recipe title/variant; shorten annotation only to respect server max 200.
        if len(rec["title"]) > 200:
            fail("invalid_metadata", "Originalrezeptname überschreitet Yuvomi-Titellimit.")
        title = rec["title"] + (suffix if len(rec["title"] + suffix) <= 200 else "")
        bodies.append(
            {
                "date": key[0],
                "meal_type": key[1],
                "title": title,
                "recipe_id": rec["id"],
                "recipe_url": old.get("recipe_url") if old else rec.get("recipe_url"),
                "cook_user_id": cook_id,
                "notes": notes_block(old.get("notes") if old else None, data, summary),
                "ingredients": scale(rec["ingredients"], factor),
            }
        )
    return bodies
