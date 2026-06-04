"""Excalidraw Diagram Generator — génère un schéma conceptuel via LLM + fallback."""

import json
import os
import re
import time
from typing import Optional

BOX_W = 300
BOX_H = 70
H_GAP = 80
V_GAP = 120
TOP_Y = 60
LEFT_MARGIN = 100

COLORS_CYCLE = [
    {"stroke": "#1971c2", "bg": "#d0ebff"},
    {"stroke": "#2b8a3e", "bg": "#d3f9d8"},
    {"stroke": "#e67700", "bg": "#fff3bf"},
    {"stroke": "#7048e8", "bg": "#e5dbff"},
    {"stroke": "#0c8599", "bg": "#c5f6fa"},
    {"stroke": "#c2255c", "bg": "#fcc2d7"},
]

_seed_counter = 0

def _next_seed() -> int:
    global _seed_counter
    _seed_counter += 1
    return int(time.time() * 1000) % 100000 + _seed_counter

def _make_id(prefix: str = "e") -> str:
    return f"{prefix}_{_next_seed()}"


# ── Fallback : extraction markdown (si LLM indisponible) ─────

BOILERPLATE = {
    "résumé exécutif", "chapitrage temporel", "moments forts",
    "résumé détaillé", "analyse vidéo", "tldr", "langue source",
}

def _extract_from_markdown(text: str) -> list:
    lines = text.strip().split("\n")
    concepts = []
    seen = set()

    def add(label: str):
        label = re.sub(r'^[#*\d\.[\]\s:]+', '', label).strip()
        label = re.sub(r'\s+', ' ', label).strip()
        if not label or len(label) < 3 or label.lower() in seen:
            return
        if label.lower() in BOILERPLATE:
            return
        label = label[:60]
        seen.add(label.lower())
        concepts.append(label)

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("# 📺"):
            raw = s.replace("# 📺 ANALYSE VIDÉO :", "").replace("# 📺", "").strip()
            if raw and len(raw) > 3:
                add(raw)
        elif s.startswith("###"):
            raw = re.sub(r'^###\s*[🔹]*\s*', '', s).strip()
            if raw and len(raw) > 3 and raw.lower() not in BOILERPLATE:
                add(raw)
        elif re.match(r'^\d+\.\s+\*', s) or re.match(r'^\d+\.\s+', s):
            raw = re.sub(r'^\d+\.\s*\*?', '', s).strip()
            raw = re.sub(r'\*.*$', '', raw).strip()
            if raw and len(raw) > 5:
                add(raw)
        elif s.startswith("- ") or s.startswith("* "):
            raw = s.lstrip("-* ").strip("* \n")
            if "**" in raw:
                raw = raw.split("**")[0] if raw.startswith("**") else raw.split("**")[1] if "**" in raw else raw
            raw = raw.split("[")[0].strip()
            if raw and len(raw) > 5 and not raw.startswith(("[", "|", ":")):
                add(raw)

    return concepts


# ── Extraction via LLM ───────────────────────────────────────

PROMPT_TEMPLATE = """Extrais 4 à 8 concepts clés de ce résumé de vidéo.
Réponds UNIQUEMENT avec les concepts, un par ligne.
Le premier concept doit être le sujet principal, les suivants sont les sous-concepts importants.
N'ajoute JAMAIS de numéros, tirets, astérisques ou explications.
N'ajoute JAMAIS de texte avant ou après la liste.
Maximum 8 lignes.

Résumé :
{text}

Concepts :"""


def _extract_via_llm(text: str, api_key: str, model: str, use_local: bool = False, local_model: Optional[str] = None) -> list:
    prompt = PROMPT_TEMPLATE.format(text=text[:4000])
    try:
        if use_local:
            from src.local_llm import call_local_llm
            response = call_local_llm(prompt, model=local_model or "llama3.2", max_tokens=500, temperature=0.3)
        else:
            from src.analyzer import call_llm
            response = call_llm(
                prompt, model=model, api_key=api_key,
                max_tokens=500, temperature=0.3,
            )
    except Exception:
        return []

    labels = []
    seen = set()
    for line in response.strip().split("\n"):
        raw = line.strip().strip("-*•1234567890. ").strip()
        if not raw or len(raw) < 3:
            continue
        if raw.lower() in seen or raw.lower() in BOILERPLATE:
            continue
        if len(raw) > 80:
            raw = raw[:80]
        seen.add(raw.lower())
        labels.append(raw)
        if len(labels) >= 8:
            break
    return labels


# ── Construction arbre ───────────────────────────────────────

def _build_tree(labels: list) -> list:
    if not labels:
        return []
    tree = [{"id": "c1", "label": labels[0], "parent_id": None}]
    for i, label in enumerate(labels[1:], start=2):
        tree.append({"id": f"c{i}", "label": label, "parent_id": "c1"})
    return tree


# ── Layout ───────────────────────────────────────────────────

def _layout_tree(concepts: list) -> list:
    children_map = {}
    for c in concepts:
        children_map.setdefault(c.get("parent_id"), []).append(c)

    def _subtree_width(node_id: str) -> int:
        kids = children_map.get(node_id, [])
        return 1 if not kids else sum(_subtree_width(k["id"]) for k in kids)

    def _place(node_id: str, x_start: float, level: int, positions: list):
        kids = children_map.get(node_id, [])
        node = next((c for c in concepts if c["id"] == node_id), None)
        if not node:
            return
        sw = _subtree_width(node_id)
        nx = x_start + (sw - 1) * (BOX_W + H_GAP) / 2 + BOX_W / 2
        ny = TOP_Y + level * (BOX_H + V_GAP)
        positions.append({"id": node_id, "x": nx, "y": ny, "level": level})
        xo = x_start
        for kid in kids:
            _place(kid["id"], xo, level + 1, positions)
            xo += _subtree_width(kid["id"]) * (BOX_W + H_GAP)

    roots = [c for c in concepts if c.get("parent_id") is None]
    if not roots:
        return []
    positions = []
    _place(roots[0]["id"], LEFT_MARGIN, 0, positions)
    return positions


# ── Éléments Excalidraw ──────────────────────────────────────

def _build_elements(concepts: list, main_topic: str) -> list:
    positions = _layout_tree(concepts)
    elements = []
    pos_map = {p["id"]: p for p in positions}
    box_map = {}

    if main_topic:
        elements.append({
            "id": _make_id("title"), "type": "text",
            "x": 0, "y": 8, "width": 1400, "height": 35,
            "angle": 0, "strokeColor": "#1e1e1e",
            "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 1, "roughness": 0, "opacity": 100,
            "groupIds": [], "roundness": None, "seed": _next_seed(),
            "version": 1, "versionNonce": 1, "isDeleted": False,
            "boundElements": None, "updated": int(time.time() * 1000),
            "link": None, "locked": False,
            "text": main_topic[:60], "fontSize": 20, "fontFamily": 2,
            "textAlign": "center", "verticalAlign": "middle",
            "containerId": None, "originalText": main_topic[:60],
            "autoResize": True, "lineHeight": 1.2,
        })

    for i, c in enumerate(concepts):
        color = COLORS_CYCLE[i % len(COLORS_CYCLE)]
        pos = pos_map.get(c["id"])
        if not pos:
            continue
        box_id = _make_id("box")
        text_id = _make_id("txt")
        box_map[c["id"]] = box_id

        elements.append({
            "id": box_id, "type": "rectangle",
            "x": pos["x"] - BOX_W / 2, "y": pos["y"],
            "width": BOX_W, "height": BOX_H,
            "angle": 0, "strokeColor": color["stroke"],
            "backgroundColor": color["bg"],
            "fillStyle": "solid", "strokeWidth": 2, "roughness": 1,
            "opacity": 100, "groupIds": [], "roundness": {"type": 3, "value": 8},
            "seed": _next_seed(), "version": 1, "versionNonce": 1,
            "isDeleted": False,
            "boundElements": [{"id": text_id, "type": "text"}],
            "updated": int(time.time() * 1000), "link": None, "locked": False,
        })
        elements.append({
            "id": text_id, "type": "text",
            "x": pos["x"] - BOX_W / 2 + 8, "y": pos["y"] + 6,
            "width": BOX_W - 16, "height": BOX_H - 12,
            "angle": 0, "strokeColor": color["stroke"],
            "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 1, "roughness": 0, "opacity": 100,
            "groupIds": [], "roundness": None,
            "seed": _next_seed(), "version": 1, "versionNonce": 1,
            "isDeleted": False, "boundElements": None,
            "updated": int(time.time() * 1000), "link": None, "locked": False,
            "text": c["label"][:50], "fontSize": 13, "fontFamily": 2,
            "textAlign": "center", "verticalAlign": "middle",
            "containerId": box_id, "originalText": c["label"][:50],
            "autoResize": True, "lineHeight": 1.2,
        })

    for c in concepts:
        parent_id = c.get("parent_id")
        if not parent_id:
            continue
        pc = pos_map.get(c["id"])
        pp = pos_map.get(parent_id)
        if not pc or not pp:
            continue
        dx = pc["x"] - pp["x"]
        dy = pc["y"] - pp["y"]
        elements.append({
            "id": _make_id("arr"), "type": "arrow",
            "x": pp["x"], "y": pp["y"] + BOX_H,
            "width": abs(dx), "height": max(1, abs(dy) - BOX_H),
            "angle": 0, "strokeColor": "#868e96",
            "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "roughness": 1, "opacity": 60,
            "groupIds": [], "roundness": {"type": 2, "value": 0},
            "seed": _next_seed(), "version": 1, "versionNonce": 1,
            "isDeleted": False, "boundElements": None,
            "updated": int(time.time() * 1000), "link": None, "locked": False,
            "points": [[0, 0], [dx, max(1, dy - BOX_H)]],
            "lastCommittedPoint": None,
            "startBinding": {"elementId": box_map.get(parent_id, ""), "gap": 0, "focus": 0},
            "endBinding": {"elementId": box_map.get(c["id"], ""), "gap": 0, "focus": 0},
            "startArrowhead": None, "endArrowhead": "arrow",
        })

    return elements


# ── API publique ─────────────────────────────────────────────

def generate_diagram(
    analysis_text: str,
    video_title: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    use_local: bool = False,
    local_model: Optional[str] = None,
) -> dict:
    labels = _extract_via_llm(analysis_text, api_key, model, use_local=use_local, local_model=local_model)

    if len(labels) < 2:
        labels = _extract_from_markdown(analysis_text)

    if len(labels) < 2:
        return {"success": False, "error": "Pas assez de concepts trouvés (LLM + fallback échoués)"}

    tree = _build_tree(labels)
    main_topic = labels[0] or video_title[:80]

    try:
        elements = _build_elements(tree, main_topic)
    except Exception as e:
        return {"success": False, "error": f"Erreur de layout : {e}"}

    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://youtube-summarizer.local",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#fafafa"},
    }

    return {
        "success": True,
        "diagram_json": json.dumps(doc, indent=2),
        "concepts": tree,
        "main_topic": main_topic,
        "source": "llm" if labels else "fallback",
    }
