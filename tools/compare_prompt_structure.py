"""Compare UTF-8 prompt bytes against the immutable RC; not a tokenizer or cache benchmark."""

import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "38f2cdb898d35cbc512c110fbd41463fcb80c138"


def literals(source):
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
    }


def compare():
    old = subprocess.check_output(
        ["git", "show", f"{BASELINE}:custom_components/yuvomi_mcp/llm.py"], cwd=ROOT
    ).decode("utf-8")
    before = literals(old)["PROMPT"]
    texts = literals((ROOT / "custom_components/yuvomi_mcp/prompts.py").read_text(encoding="utf-8"))
    report = {}
    for label, names in {
        "tasks_calendar": ["BASE_PROMPT"],
        "default_shopping_tasks_calendar": ["BASE_PROMPT", "SHOPPING_PROMPT"],
        "default_plus_recipes": ["BASE_PROMPT", "SHOPPING_PROMPT", "RECIPE_PROMPT"],
        "default_plus_recipes_menu": ["BASE_PROMPT", "SHOPPING_PROMPT", "RECIPE_PROMPT", "MENU_PROMPT"],
    }.items():
        baseline = before
        if "MENU_PROMPT" in names:
            baseline = baseline.replace(
                "Noch keine Menüplanerstellung, Kalender-/Vorratsabfrage, Portionsskalierung oder Zutatenübertragung automatisieren.",
                "Menüplanung nur mit freigegebenen Menüwerkzeugen; der geladene Planungskontext definiert harte Regeln. "
                "Kein automatischer Einkaufsübertrag. Ganze Wochen bewusst in separater Planungs-Conversation planen.",
            )
        a = len(baseline.encode("utf-8"))
        b = len("\n".join(texts[name] for name in names).encode("utf-8"))
        report[label] = {"before_bytes": a, "after_bytes": b, "saved_percent": round(100 * (a - b) / a, 2)}
    return {
        "baseline_commit": BASELINE,
        "excludes": "dynamic clock suffix, agent/family prompt and tools",
        "static_api_prompt": report,
    }


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
