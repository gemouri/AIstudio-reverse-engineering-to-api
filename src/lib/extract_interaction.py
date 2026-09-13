"""Interactions API — extract answer/thinking/usage/model từ response frames.

Response shape (runtime-decoded 12/09, corpus iswap_resp_*.json):
  data = [ events ]
  events[i]:
    [18][0][0]   = interaction id ("v1_...")       — interaction-created frame
    [18][0][17]  = ["models/<id>", genconfig]     — idem
    [10][0]==1   = answer delta:  text = e[10][1][0][0]
    [10][1][5]   = thinking delta: text = e[10][1][5][0][0][0]
    [11]         = [turn_seq]                     — turn complete
    [19][0][11]  = usage list                     — final metadata frame
"""


def _iter_events(raw: str):
    """Parse 1+ JSON frames nối tiếp → list các event (list)."""
    events = []
    try:
        data = json.loads(raw)
    except Exception:
        dec = json.JSONDecoder()
        s, i = raw.strip(), 0
        while i < len(s):
            while i < len(s) and s[i] in " \r\n\t":
                i += 1
            if i >= len(s):
                break
            try:
                obj, end = dec.raw_decode(s, i)
            except Exception:
                break
            if isinstance(obj, list):
                events.extend(obj[0] if (obj and isinstance(obj[0], list)) else obj)
            i = end
        return events

    # single frame: data = [events...] → dùng luôn
    if isinstance(data, list):
        for item in data:
            if isinstance(item, list):
                events.extend(item)
    return events


def extract_interaction(raw: str) -> dict:
    """CreateInteractionStream response → {answer, thinking, model, usage, error,
    images, sources}.

    2 response shapes (runtime-verified 12/09):
    A) omni — streaming deltas: e[10][0]==1 → answer delta e[10][1][0][0],
       thinking delta e[10][1][5][0][0][0].
    B) deep-research/agent — structured RESULT frame: data[k][0] = parts list:
       parts[1][0] = thinking full text   (parts[1][29][N][1] = segments)
       parts[2][0] = answer full text     (markdown report)
       parts[3][12][1] = image artifact b64 (PNG; parts[3][29][0][2][1] idem)
       parts[4][0] = sources markdown     (parts[4][33][N][1] = raw URLs)
    """
    out = {"answer": "", "thinking": "", "model": None, "usage": None,
           "error": None, "images": [], "sources": None}
    events = _iter_events(raw)

    # 13/09 FIX: error frame [N, "msg", ...] nằm TOP-LEVEL của body (item riêng
    # bên cạnh các stream chunks) — _iter_events flatten từng chunk (events.extend)
    # nên frame lỗi bị UNPACK/ghép chung mất → err=None → facade trả "empty
    # schema drift" 502 thay vì 429 quota thật (omni-1.1-flash trên Pro /u/2/,
    # runtime-verified: item[1] = [8, "You exceeded your current quota…", [...]]).
    try:
        _body = json.loads(raw) if raw.strip().startswith("[") else None
        if isinstance(_body, list):
            for _it in _body:
                if (isinstance(_it, list) and _it and isinstance(_it[0], int)
                        and isinstance(_it[1], str) and len(_it[1]) > 10
                        and not _it[1].startswith("[")):
                    out["error"] = f"[{_it[0]}] {_it[1][:200]}"
    except Exception:
        pass

    answer, thinking = [], []

    # Quota/permission error frame: [N, "error text"] nằm ở top-level của
    # frame (N=3 permission, N=8 quota — cùng shape GenerateContent).
    for e in events:
        if isinstance(e, list) and len(e) == 2 and isinstance(e[0], int) and isinstance(e[1], str) \
                and not e[1].startswith("["):
            out["error"] = f"[{e[0]}] {e[1][:200]}"

    for e in events:
        if not isinstance(e, list) or not e:
            continue

        # model (frames [18])
        if len(e) > 18 and isinstance(e[18], list) and e[18]:
            try:
                inner = e[18][0]
                if isinstance(inner, list) and len(inner) > 17 and isinstance(inner[17], list):
                    m = inner[17][0]
                    if isinstance(m, str) and m.startswith("models/"):
                        out["model"] = m
            except (TypeError, IndexError):
                pass

        # usage (frames [19])
        if len(e) > 19 and isinstance(e[19], list) and e[19]:
            try:
                u = e[19][0][11]
                if isinstance(u, list):
                    out["usage"] = u
            except (TypeError, IndexError):
                pass

        # deltas (shape A — omni)
        if len(e) > 10 and isinstance(e[10], list) and len(e[10]) >= 2:
            v = e[10]
            try:
                if v[0] == 1 and isinstance(v[1], list) and v[1] and isinstance(v[1][0], list):
                    answer.append(v[1][0][0])          # answer text delta
                elif v[1] and isinstance(v[1][5], list) and v[1][5]:
                    thinking.append(v[1][5][0][0][0])  # thinking text delta
            except (TypeError, IndexError):
                pass

    # ---- shape B: structured result frame (deep-research / agent) ----
    # _iter_events FLATTEN chunks → event e CHÍNH LÀ parts list:
    #   e[1][0] = thinking full text, e[2][0] = answer (markdown),
    #   e[3][12][1] = image artifact b64, e[4][0] = sources markdown
    if not answer:
        for e in events:
            if not (isinstance(e, list) and len(e) > 4):
                continue
            try:
                # answer part (markdown) — guard chắc chắn là result frame
                if (isinstance(e[2], list) and e[2] and isinstance(e[2][0], str)
                        and len(e[2][0]) > 10):
                    answer.append(e[2][0])
                    # thinking part
                    if isinstance(e[1], list) and e[1] and isinstance(e[1][0], str):
                        thinking.append(e[1][0])
                    # image artifact part: b64 tại e[3][12][1]
                    if isinstance(e[3], list):
                        try:
                            b64 = e[3][12][1]
                            if isinstance(b64, str) and len(b64) > 100:
                                out["images"].append(b64)
                        except (TypeError, IndexError):
                            pass
                    # sources part (markdown)
                    if isinstance(e[4], list) and e[4] and isinstance(e[4][0], str):
                        out["sources"] = e[4][0]
                    break
            except (TypeError, IndexError):
                continue

    out["answer"] = "".join(answer)
    out["thinking"] = "".join(thinking)
    return out


import json  # noqa: E402  (used by _iter_events)

if __name__ == "__main__":
    import sys
    for fn in sys.argv[1:]:
        r = extract_interaction(open(fn, encoding="utf-8").read())
        print(f"=== {fn} ===")
        print(f"  model: {r['model']}")
        print(f"  answer: {r['answer'][:120]!r}")
        print(f"  thinking len: {len(r['thinking'])}")
        print(f"  usage: {r['usage']}")
