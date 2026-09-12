"""OpenAI tools <-> Gemini internal tools converter + response functionCall parser.

Schema field map (from source gp() + validated corpus):
  proto: [1]=type(1=str,2=num,3=int,4=bool,5=arr,6=obj), [3]=description, [4]=nullable,
  [5]=enum, [6]=items, [7]=properties(map), [8]=required, [11]=minimum, [12]=maximum,
  [13]=minLength, [14]=maxLength, [17]=oneOf, [18]=anyOf, [19]=allOf, [23]=propertyOrdering

FunctionDeclaration proto: [1]=name, [2]=description, [3]=parameters(schema)
Tool proto: [2]=functionDeclarations list
"""
from __future__ import annotations

import json

TYPE_MAP = {"string": 1, "number": 2, "integer": 3, "boolean": 4, "array": 5, "object": 6}


def schema_to_proto(schema: dict) -> list:
    """JSON Schema -> Gemini proto array (positional fields)."""
    if not isinstance(schema, dict):
        # e.g. raw string shorthand
        return [1, None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None, None,
                None, None, None, None]
    p: list = [None] * 24
    t = schema.get("type")
    if isinstance(t, str) and t in TYPE_MAP:
        p[0] = TYPE_MAP[t]
    if "format" in schema:
        p[1] = schema["format"]
    if "description" in schema:
        p[2] = schema["description"]
    if schema.get("nullable"):
        p[3] = True
    if "enum" in schema and isinstance(schema["enum"], list):
        p[4] = list(schema["enum"])
    if "items" in schema:
        p[5] = schema_to_proto(schema["items"])
    if "properties" in schema and isinstance(schema["properties"], dict):
        p[6] = [[k, schema_to_proto(v)] for k, v in schema["properties"].items()]
    if "required" in schema and isinstance(schema["required"], list):
        p[7] = list(schema["required"])
    if "minimum" in schema:
        p[10] = schema["minimum"]
    if "maximum" in schema:
        p[11] = schema["maximum"]
    if "minLength" in schema:
        p[12] = schema["minLength"]
    if "maxLength" in schema:
        p[13] = schema["maxLength"]
    if "oneOf" in schema:
        p[16] = [schema_to_proto(s) for s in schema["oneOf"]]
    if "anyOf" in schema:
        p[17] = [schema_to_proto(s) for s in schema["anyOf"]]
    if "allOf" in schema:
        p[18] = [schema_to_proto(s) for s in schema["allOf"]]
    if schema.get("additionalProperties") is False:
        p[19] = False
    if "propertyOrdering" in schema:
        p[22] = list(schema["propertyOrdering"])
    # keep full proto length (UI pads to 23+; unset fields = null are equivalent,
    # but matching the UI shape byte-for-byte is safest against server validation)
    while len(p) < 23:
        p.append(None)
    return p


def openai_tools_to_gemini(openai_tools: list) -> list:
    """OpenAI [{type:function, function:{name,description,parameters}}]
    -> Gemini payload[6] tools shape (validated in fcall_manual_capture)."""
    decls = []
    for t in openai_tools:
        if t.get("type") != "function":
            continue  # only function tools supported
        fn = t.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        decl = [name, fn.get("description", ""), schema_to_proto(fn.get("parameters", {}))]
        decls.append(decl)
    if not decls:
        return []
    return [[None, decls]]


# ---- response parsing ----

def find_function_calls(body: str) -> list:
    """Extract functionCall parts from a GenerateContent response.

    Part shape (validated fcall_manual_capture):
      [None×10, [name, [[[param, [None, None, value]]]], call_id], ...]
    Returns OpenAI tool_calls shape: [{id, type:'function', function:{name, arguments:str}}]
    """
    try:
        data = json.loads(body)
    except Exception:
        return []

    def proto_args_to_dict(args_proto):
        """fc[1] shape: [[['city', [None,None,'Tokyo']]]] (double-wrapped kv list)
        or [['city', [None,None,'Tokyo']]]. Normalize both -> {'city':'Tokyo'}"""
        def kv_list(node):
            # node is a list of [key, value] entries
            out = {}
            if not isinstance(node, list):
                return out
            for entry in node:
                if not (isinstance(entry, list) and len(entry) == 2):
                    continue
                key, val = entry
                if isinstance(val, list):
                    out[key] = _unwrap(val)
                else:
                    out[key] = val
            return out
        if not isinstance(args_proto, list):
            return {}
        # unwrap outer lists until we hit [key, value] entries
        node = args_proto
        depth = 0
        while (isinstance(node, list) and len(node) == 1
               and isinstance(node[0], list) and depth < 4):
            node = node[0]
            depth += 1
        # node may BE a single [key, value] entry (e.g. ["city", [None,None,"Tokyo"]])
        if (isinstance(node, list) and len(node) == 2
                and isinstance(node[0], str)):
            node = [node]
        return kv_list(node)

    def _unwrap(v):
        if isinstance(v, list):
            if len(v) == 3 and v[0] is None and v[1] is None:
                return v[2]
            # nested object/array of values
            if all(isinstance(x, list) and len(x) == 2 for x in v):
                return {k: _unwrap(x) for k, x in v}
            return [_unwrap(x) for x in v]
        return v

    calls = []
    def walk(node):
        if isinstance(node, list):
            # functionCall part: [None]*10 then [name, args, id]
            if len(node) >= 11 and all(x is None for x in node[:10]) and isinstance(node[10], list):
                fc = node[10]
                if len(fc) >= 2 and isinstance(fc[0], str) and isinstance(fc[1], list):
                    name = fc[0]
                    args = proto_args_to_dict(fc[1])
                    cid = fc[2] if len(fc) >= 3 and isinstance(fc[2], str) else f"call_{len(calls)+1}"
                    calls.append({"id": cid, "type": "function",
                                  "function": {"name": name,
                                               "arguments": json.dumps(args, ensure_ascii=False)}})
                    return
            for ch in node:
                walk(ch)
    for chunk in data:
        walk(chunk)
    return calls


if __name__ == "__main__":
    # validation against real corpus
    from pathlib import Path
    CORPUS = Path(r".\corpus")

    # 1. manual capture response -> function call
    evs = json.loads((CORPUS / "fcall_manual_capture.json").read_text(encoding="utf-8"))
    rb = evs[0].get("respBody") or ""
    calls = find_function_calls(rb)
    print("manual capture calls:", json.dumps(calls, indent=1))

    # 2. round-trip: our converter output must match the manual payload's tools
    openai_form = [{"type": "function", "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string", "description": "City name"}},
                       "required": ["city"]}}}]
    manual_payload = json.loads(evs[0]["postData"])
    mine = openai_tools_to_gemini(openai_form)
    theirs = manual_payload[6]
    # normalize: strip trailing Nones in schema arrays for comparison
    def norm(x):
        if isinstance(x, list):
            y = [norm(c) for c in x]
            while y and y[-1] is None:
                y.pop()
            return y
        return x
    print("converter == UI-built:", norm(mine) == norm(theirs))
