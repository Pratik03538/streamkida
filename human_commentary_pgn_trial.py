"""
STREAMKIDA - LOCAL HUMAN COMMENTARY PGN TRIAL

No AI/LLM/API is used.
Stockfish supplies objective chess information only.
human_commentary.py turns that information into Roman-Hinglish commentary.
"""

from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

import chess
import chess.engine
import chess.pgn

from human_commentary_human import EngineSnapshot, make_commentary


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


def find_stockfish() -> str:
    root = Path(__file__).resolve().parent

    candidates = [
        root / "stockfish.exe",
        root / "Stockfish" / "stockfish.exe",
    ]

    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path:
        candidates.insert(0, Path(env_path))

    path = shutil.which("stockfish")
    if path:
        candidates.insert(0, Path(path))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "stockfish.exe nahi mila. Project root me stockfish.exe rakho "
        "ya STOCKFISH_PATH set karo."
    )


def score_cp(score: chess.engine.Score | None) -> int | None:
    if score is None:
        return None
    try:
        return score.score(mate_score=100000)
    except Exception:
        return None


def score_text(score: chess.engine.Score | None) -> str:
    if score is None:
        return "?"
    try:
        if score.is_mate():
            mate = score.mate()
            return f"M{mate:+d}" if mate is not None else "M?"
        cp = score.score(mate_score=100000)
        return f"{cp / 100:+.2f}" if cp is not None else "?"
    except Exception:
        return "?"


def pv_to_san(board: chess.Board, pv: list[chess.Move], count: int = 5) -> str:
    temp = board.copy()
    result = []
    for move in pv[:count]:
        try:
            result.append(temp.san(move))
            temp.push(move)
        except Exception:
            break
    return " ".join(result)


def main() -> None:
    print("=" * 86)
    print("        STREAMKIDA - LOCAL HUMAN COMMENTARY TRIAL")
    print("        STOCKFISH + OWN HUMAN VOICE ENGINE | NO AI")
    print("=" * 86)

    game = chess.pgn.read_game(io.StringIO(PGN_TEXT))
    if game is None:
        raise RuntimeError("PGN parse failed.")

    engine_path = find_stockfish()
    engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    board = game.board()
    commentator_move_history: list[str] = []

    try:
        for ply, move in enumerate(game.mainline_moves(), 1):
            before = board.copy()
            san = before.san(move)

            info_before = engine.analyse(
                before,
                chess.engine.Limit(depth=14),
            )
            score_before_obj = info_before.get("score")
            score_before = score_cp(score_before_obj)
            pv = info_before.get("pv") or []
            best_move = pv[0] if pv else None
            pv_san = pv_to_san(before, pv)

            board.push(move)
            after = board.copy()

            info_after = engine.analyse(
                after,
                chess.engine.Limit(depth=14),
            )
            score_after = score_cp(info_after.get("score"))

            snapshot = EngineSnapshot(
                eval_before_cp=score_before,
                eval_after_cp=score_after,
                best_move_before=best_move,
                best_move_after=(info_after.get("pv") or [None])[0],
                pv_san=pv_san,
                depth=14,
            )

            result = make_commentary(
                before=before,
                move=move,
                after=after,
                engine_snapshot=snapshot,
                recent_sans=tuple(commentator_move_history[-8:]),
            )

            move_label = f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}"

            print()
            print("-" * 86)
            print(
                f"{move_label:<6} {san:<9} "
                f"Stockfish: {score_text(score_before_obj.pov(chess.WHITE))} -> "
                f"{score_text(info_after.get('score').pov(chess.WHITE))}"
            )
            print(f"COMMENTARY : {result.commentary}")
            print(f"PLAN       : {result.plan}")
            print(f"THREAT     : {result.threat}")
            print(f"WATCH      : {result.watch}")
            print(f"TAGS       : {', '.join(result.tags) or '-'}")

            commentator_move_history.append(san)

    finally:
        engine.quit()

    print()
    print("=" * 86)
    print("TRIAL COMPLETE - koi AI/LLM/API call nahi hua.")
    print("=" * 86)


if __name__ == "__main__":
    main()
