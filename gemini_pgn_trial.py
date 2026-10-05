"""
STREAMKIDA - GEMINI + STOCKFISH PGN COMMENTARY TRIAL

Purpose:
    Replay a PGN through python-chess + local Stockfish, identify the most
    commentary-worthy moments, and ask Gemini 3.5 Flash-Lite for natural,
    funny, smart Roman-Hinglish commentary.

Safety:
    - Does NOT modify main.py.
    - Gemini never chooses moves.
    - Stockfish is used only for chess analysis/context.
    - API failures never stop the PGN replay.
    - key.txt is read locally and must never be committed.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import chess
import chess.engine
import chess.pgn
from google import genai
from google.genai import types


MODEL = "gemini-3.5-flash-lite"
THINKING_LEVEL = "minimal"
MAX_GEMINI_CALLS = 10
STOCKFISH_DEPTH = 12

PGN_TEXT = r'''
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.10.05"]
[Round "?"]
[White "Hikaru"]
[Black "subham777"]
[Result "1-0"]
[TimeControl "180"]
[WhiteElo "3495"]
[BlackElo "2897"]
[Termination "Hikaru won by resignation"]
[ECO "A01"]
[EndTime "0:50:40 GMT+0000"]
[Link "https://www.chess.com/game/live/184830086652?username=hikaru&move=0"]

1. b3 d6 2. Bb2 Nf6 3. d4 g6 4. Nf3 Bg7 5. e3 O-O 6. Be2 Re8 7. O-O c6 8. c4 a5
9. Nc3 Bf5 10. Re1 Na6 11. a3 e5 12. Bf1 e4 13. Nd2 d5 14. cxd5 cxd5 15. Nb5 Nc7
16. Rc1 Nxb5 17. Bxb5 Bd7 18. Be2 Bf8 19. Nb1 h5 20. Nc3 Bd6 21. h3 Rc8 22. Nb5
Bb8 23. Rxc8 Qxc8 24. Qc1 Bxh3 25. Qxc8 Bxc8 26. Bc3 b6 27. b4 axb4 28. Bxb4 Bd7
29. Nc3 Rc8 30. Rb1 Kg7 31. Rb3 Bg4 32. Kf1 Be6 33. Ba6 Rh8 34. Ke1 h4 35. Bf1
g5 36. Be7 g4 37. Bxf6+ Kxf6 38. Rxb6 Kg7 39. Nb5 h3 40. g3 h2 41. Bg2 h1=Q+ 42.
Bxh1 Rxh1+ 43. Ke2 Rh8 44. Rb7 Rc8 45. a4 Rc2+ 46. Kd1 Ra2 47. Rxb8 Rxa4 48. Nc3
Ra1+ 49. Rb1 Ra3 50. Kc2 Kf6 51. Ne2 Ra2+ 52. Rb2 Ra6 53. Nf4 Rc6+ 54. Kd2 Ra6
55. Rc2 Ke7 56. Ke2 Kd6 57. Kf1 Bd7 58. Rc5 Bc6 59. Kg2 Ra2 60. Rc1 f5 61. Rh1
Ba4 62. Rh6+ Kd7 63. Rh1 Kd6 64. Rh6+ Kd7 65. Ra6 Bb3 66. Rxa2 Bxa2 67. Kf1 Bc4+
68. Ke1 Kd6 69. Kd2 Ke7 70. Kc3 Kf6 71. Kb4 Ke7 72. Kc5 Kf6 73. Nxd5+ 1-0
'''


def load_api_key() -> str:
    path = Path(__file__).resolve().parent / "key.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"key.txt not found at {path}. Put your Gemini API key in that local file."
        )
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("key.txt is empty.")
    return key


def find_stockfish() -> str:
    candidates = [
        Path(__file__).resolve().parent / "stockfish.exe",
        Path(__file__).resolve().parent / "Stockfish" / "stockfish.exe",
    ]

    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path:
        candidates.insert(0, Path(env_path))

    which_path = shutil.which("stockfish")
    if which_path:
        candidates.insert(0, Path(which_path))

    for path in candidates:
        if path.exists() and path.is_file():
            return str(path)

    raise FileNotFoundError(
        "Stockfish executable not found. Put stockfish.exe in the project root "
        "or set STOCKFISH_PATH."
    )


def clean_score(score: chess.engine.Score | None) -> str:
    if score is None:
        return "?"
    try:
        if score.is_mate():
            m = score.mate()
            return f"M{abs(m)}" if m is not None else "M?"
        cp = score.score(mate_score=100000)
        if cp is None:
            return "?"
        return f"{cp / 100:+.2f}"
    except Exception:
        return "?"


def score_cp(score: chess.engine.Score | None) -> int | None:
    if score is None:
        return None
    try:
        return score.score(mate_score=100000)
    except Exception:
        return None


def best_pv_san(board: chess.Board, info: dict, plies: int = 6) -> str:
    pv = info.get("pv") or []
    if not pv:
        return ""
    temp = board.copy()
    out = []
    for move in pv[:plies]:
        try:
            out.append(temp.san(move))
            temp.push(move)
        except Exception:
            break
    return " ".join(out)


def safe_result_text(response) -> str:
    text = getattr(response, "text", None)
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def choose_moments(records: list[dict], limit: int) -> list[int]:
    scored = []
    for i, r in enumerate(records):
        interest = 0

        if r["is_capture"]:
            interest += 25
        if r["is_check"]:
            interest += 30
        if r["is_promotion"]:
            interest += 80
        if not r["is_best"]:
            interest += 10

        swing = r["swing_cp"]
        if swing is not None:
            interest += min(abs(swing) // 5, 70)
            if swing <= -100:
                interest += 55
            elif swing >= 80:
                interest += 30

        if r["classification"] in {"BRILLIANT", "BEST", "BLUNDER", "MISTAKE"}:
            interest += 45

        # Opening and endgame anchors make the final trial more readable.
        if r["ply"] in {1, 2, 10, 20, 30, 40, 50, 60, 70, 80, 100, 120, 140}:
            interest += 8

        scored.append((interest, i))

    scored.sort(reverse=True)
    selected = sorted(i for _, i in scored[:limit])
    return selected


def build_prompt(r: dict, recent_moves: str) -> str:
    mover = r["mover"]
    result_hint = (
        "The move improved the mover's position according to the supplied engine data."
        if (r["swing_cp"] is not None and r["swing_cp"] >= 50)
        else "The move was a normal/unclear practical decision."
    )

    return f"""
You are the live commentator for a 3-minute online chess game.

Write ONE compact, exciting Roman-Hinglish commentary for this VERIFIED move.

Style:
- Natural Indian chess-fan Hinglish, in Roman letters only.
- Gavran/desi flavour: light words like "arre bhau", "arey yaar", "kya jhol hai", "ab dekh bhau" are okay, but use them naturally, not every sentence.
- Funny + smart + dramatic, like a sharp friend watching a live game.
- Emotion must come from the chess position: tension, surprise, greed, pressure, relief, danger, attack, defense.
- Mention a concrete plan or threat when supported by the data.
- Keep it 25-55 words.
- Use standard chess notation for moves.
- Do NOT say "Stockfish says" unless needed; use the engine data naturally.
- Do not praise every move. Strong moves can sound strong, ordinary moves can sound calm, mistakes can sound teasing.
- No poetry, philosophy, generic motivation, or unrelated jokes.

Hard factual rules:
- You MUST use only the supplied FEN, move, engine evaluation, PV, and recent moves.
- Never invent a piece, attack, threat, tactic, or square that is not supported.
- Never call a move brilliant, winning, blundering, or crushing without engine support.
- Do not predict a forced line unless the supplied PV supports it.
- The Gemini commentary is commentary only; it never chooses a move.

DATA
Move number: {r["move_no"]}
Mover: {mover}
Move: {r["san"]}
FEN after the move: {r["fen_after"]}
Evaluation BEFORE (White POV): {r["eval_before"]}
Evaluation AFTER (White POV): {r["eval_after"]}
Move swing for mover: {r["swing_cp"]} centipawns
Classification: {r["classification"]}
Engine best move BEFORE: {r["best_san"]}
Engine PV BEFORE: {r["pv"]}
Recent moves: {recent_moves}
Context note: {result_hint}

Return only the commentary paragraph.
""".strip()


def classify(swing_cp: int | None, is_best: bool, is_check: bool, is_capture: bool) -> str:
    if swing_cp is not None:
        if swing_cp <= -200:
            return "BLUNDER"
        if swing_cp <= -80:
            return "MISTAKE"
        if swing_cp >= 120 and (is_capture or is_check):
            return "BRILLIANT"
    if is_best:
        return "BEST"
    if swing_cp is not None and swing_cp >= 50:
        return "STRONG"
    return "NORMAL"


def main() -> None:
    print("=" * 72)
    print("   STREAMKIDA - STOCKFISH + GEMINI PGN COMMENTARY TRIAL")
    print("=" * 72)

    api_key = load_api_key()
    client = genai.Client(api_key=api_key)
    stockfish_path = find_stockfish()

    game = chess.pgn.read_game(__import__("io").StringIO(PGN_TEXT))
    if game is None:
        raise RuntimeError("PGN could not be parsed.")

    board = game.board()
    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)

    records: list[dict] = []

    try:
        recent_history: list[str] = []

        for ply, move in enumerate(game.mainline_moves(), start=1):
            move_no = f"{(ply + 1) // 2}.{'..' if ply % 2 == 0 else ''}"
            mover = "White" if board.turn == chess.WHITE else "Black"
            san = board.san(move)

            before = engine.analyse(
                board,
                chess.engine.Limit(depth=STOCKFISH_DEPTH),
                multipv=1,
            )[0]

            before_score = before.get("score")
            before_cp = score_cp(before_score.pov(chess.WHITE))
            best_move = before.get("pv", [None])[0]
            best_san = board.san(best_move) if best_move is not None else "?"
            pv = best_pv_san(board, before)

            is_capture = board.is_capture(move)
            is_check = board.gives_check(move)
            is_promotion = move.promotion is not None
            is_best = best_move == move

            board.push(move)

            after = engine.analyse(
                board,
                chess.engine.Limit(depth=STOCKFISH_DEPTH),
                multipv=1,
            )[0]

            after_score = after.get("score")
            after_cp = score_cp(after_score.pov(chess.WHITE))

            swing_cp = None
            if before_cp is not None and after_cp is not None:
                delta_white = after_cp - before_cp
                swing_cp = delta_white if mover == "White" else -delta_white

            classification = classify(
                swing_cp,
                is_best,
                is_check,
                is_capture,
            )

            recent_history.append(san)
            recent = " ".join(recent_history[-8:])

            records.append(
                {
                    "ply": ply,
                    "move_no": move_no,
                    "mover": mover,
                    "san": san,
                    "fen_after": board.fen(),
                    "eval_before": clean_score(before_score.pov(chess.WHITE)),
                    "eval_after": clean_score(after_score.pov(chess.WHITE)),
                    "before_cp": before_cp,
                    "after_cp": after_cp,
                    "swing_cp": swing_cp,
                    "classification": classification,
                    "best_san": best_san,
                    "pv": pv,
                    "is_capture": is_capture,
                    "is_check": is_check,
                    "is_promotion": is_promotion,
                    "is_best": is_best,
                    "recent": recent,
                }
            )

            print(
                f"[ENGINE] {move_no:<5} {san:<7} "
                f"eval {clean_score(before_score.pov(chess.WHITE)):>6} -> "
                f"{clean_score(after_score.pov(chess.WHITE)):>6} | "
                f"{classification}"
            )

        selected = choose_moments(records, MAX_GEMINI_CALLS)

        print("\n" + "=" * 72)
        print(
            f"SELECTED GEMINI MOMENTS: {len(selected)} "
            f"(quota-safe trial, max {MAX_GEMINI_CALLS} calls)"
        )
        print("=" * 72)

        for n, idx in enumerate(selected, start=1):
            r = records[idx]
            print(
                f"\n[{n:02d}] MOVE {r['move_no']} {r['san']} | "
                f"{r['classification']} | "
                f"eval {r['eval_before']} -> {r['eval_after']}"
            )

            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=build_prompt(r, r["recent"]),
                    config=types.GenerateContentConfig(
                        temperature=0.85,
                        max_output_tokens=100,
                        thinking_config=types.ThinkingConfig(
                            thinking_level=THINKING_LEVEL
                        ),
                    ),
                )
                commentary = safe_result_text(response)
                if commentary:
                    print(f"[GEMINI] {commentary}")
                else:
                    print("[GEMINI] EMPTY RESPONSE")
            except Exception as exc:
                print(f"[GEMINI] FAILED: {exc}")

    finally:
        engine.quit()

    print("\n" + "=" * 72)
    print("TRIAL COMPLETE")
    print("=" * 72)
    print(
        "Gemini is commentary-only. Stockfish generated the chess context; "
        "the PGN replay never depends on Gemini."
    )


if __name__ == "__main__":
    main()
