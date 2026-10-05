"""
STREAMKIDA — HUMAN COMMENTARY ENGINE v3
========================================

Pure local chess commentary:
    python-chess = facts
    Stockfish    = objective evaluation / next ideas
    this module  = voice

NO AI.
NO LLM.
NO network.
NO move selection.

Design:
    A real commentator notices the most interesting thing about a move.
    Most moves get one short spoken thought.
    Important moments get a second sentence.
    The language is intentionally conversational, desi and Roman-Hinglish.

The module is conservative about chess claims.  It prefers saying less over
inventing a tactic.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Optional

import chess


# ============================================================================
# DATA
# ============================================================================

@dataclass(frozen=True)
class EngineSnapshot:
    eval_before_cp: Optional[int] = None
    eval_after_cp: Optional[int] = None
    best_move_before: Optional[chess.Move] = None
    best_move_after: Optional[chess.Move] = None

    # PV from the position BEFORE the move.
    pv_before_san: str = ""

    # PV from the position AFTER the move.
    pv_after_san: str = ""

    depth: int = 0

    @property
    def swing_for_mover_cp(self) -> Optional[int]:
        if self.eval_before_cp is None or self.eval_after_cp is None:
            return None

        white_delta = self.eval_after_cp - self.eval_before_cp
        return white_delta if self._mover_is_white else -white_delta

    # Set by caller through this small helper rather than storing board color
    # inside the snapshot.
    _mover_is_white: bool = True

    def mover_swing(self, mover: chess.Color) -> Optional[int]:
        if self.eval_before_cp is None or self.eval_after_cp is None:
            return None
        delta = self.eval_after_cp - self.eval_before_cp
        return delta if mover == chess.WHITE else -delta


@dataclass
class Commentary:
    commentary: str
    plan: str = ""
    threat: str = ""
    watch: str = ""
    tags: tuple[str, ...] = ()


# ============================================================================
# SPOKEN LANGUAGE BANKS
# ============================================================================

OPENERS = (
    "arre",
    "arey",
    "oho",
    "aila",
    "baap re",
    "arey bhau",
    "oho bhau",
    "haan bhai",
    "bhau",
    "arey yaar",
    "areee",
    "kya baat",
    "dekho bhai",
    "suno bhau",
    "arre baba",
    "ohoho",
    "bade bhai",
    "kya scene",
    "chal bhau",
    "wah bhau",
    "oyy",
    "arre re",
)

FILLERS = (
    "hmm",
    "accha",
    "haan",
    "waise",
    "dekho",
    "sach bolu",
    "theek",
    "ab",
    "hmm bhai",
    "haan re",
)

ORDINARY_ENDINGS = (
    "ab dekhte hain.",
    "ab reply interesting hoga.",
    "ab asli baat saamne aayegi.",
    "abhi game zinda hai.",
    "ab dekh bhau.",
    "abhi picture baaki hai.",
    "ab yaha nazar rakhna.",
    "ab game dheere-dheere khul raha hai.",
    "ab agla move bata dega kya scene hai.",
    "abhi kuch pakka nahi hai.",
)

SMALL_ASIDES = (
    "piece ko duty mil gayi.",
    "mohra attendance laga gaya.",
    "yeh piece ab tourist nahi raha.",
    "board pe setting ho rahi hai.",
    "dimaag ka attendance chahiye ab.",
    "simple lag raha hai, par khaali nahi hai.",
    "seedha kaam, tedha effect ho sakta hai.",
    "ab kisi ko comfortable rehne ka haq nahi.",
)

QUIET_SMART = (
    "Badi shaanti se kaam ka move.",
    "Shor zero, kaam poora.",
    "Dikhne me normal, placement acchi.",
    "Ye move hawa me nahi gaya.",
    "Yaha style se zyada timing matter karti hai.",
    "Simple chaal hai, par intention saaf hai.",
)

# Every special situation has its own voice, so a check never sounds like a
# development move and a blunder never sounds like "quietly strong".


NORMAL = (
    "{san}. {line}",
    "{san}... {line}",
    "{side} ka {san}. {line}",
    "{opener} {san}. {line}",
    "{san} — {line}",
)

NORMAL_LINES = (
    "abhi position ko thoda aur set kar raha hai",
    "piece ko better jagah dene ki soch hai",
    "opponent ko read kar raha hai",
    "agla idea ke liye setup bana raha hai",
    "apne pieces ko jodne ki koshish hai",
    "abhi seedha hungama nahi, pehle groundwork",
    "position pe apni grip thodi aur badha raha hai",
    "counterplay ke liye jagah bana raha hai",
)

DEVELOPMENT = (
    "{san}. {piece} ko ghar se bahar nikala, ab asli naukri karega.",
    "{san}! Accha, {piece} ko finally board pe kaam mil gaya.",
    "{side} ka {san} — development bhi aur active square bhi.",
    "{san}... {piece} ab spectator nahi raha.",
    "{san}. Piece ko sahi jagah, kaam seedha.",
)

CENTER = (
    "{san}! Beech ka maidan chhodne ka mood nahi.",
    "{san} — center me kursi kheench ke baith gaye.",
    "{side} ne {san} se center pe aur dabav daal diya.",
    "{san}! Beech ki jagah ke liye full bargaining chal rahi hai.",
)

PAWN_BREAK = (
    "{san}! Pawn ne darwaza dhakka de diya.",
    "{san} — structure ko halka sa hila diya.",
    "{side} ka {san}; ab lines khulengi toh pieces bolenge.",
    "{san}! Pawn aage gaya, ab peeche wale mohre kaam dikhayenge.",
)

CAPTURE = (
    "{san}. Seedha hisaab-kitab.",
    "{san}! Accha, samaan utha liya.",
    "{side} ka {san}; {captured} gaya, ab exchange ka bill dekho.",
    "{san} — ek mohra kam, position ka hisaab naya.",
    "{opener} {san}! Tension ko seedha capture me badal diya.",
)

BIG_CAPTURE = (
    "{san}! Arre bhau, itna bada samaan!",
    "{san}! Ye koi chhota exchange nahi tha.",
    "{san}! Rook/queen level ka hisaab ho gaya bhai.",
    "{opener} {san}! Board pe dukaan saaf.",
)

CHECK = (
    "{san}! Raja ko seedha sawaal.",
    "{opener} {san}! Ab king ko jawab dena hi padega.",
    "{san} — check bhi, tempo bhi.",
    "{side} ne {san} se conversation ekdum badal di.",
    "{san}! Raja ko zara uth-baith karwa diya.",
    "{opener} check aa gaya bhau, ab reply halka nahi chalega.",
)

PROMOTION = (
    "{san}! Aila bhau, pawn ne promotion maar diya!",
    "{san}! Arey wah, pawn seedha malik ban gaya.",
    "{san}! Is pawn ka career toh mast nikla.",
    "{san}! Pawn ne naukri chhodi, bada aadmi ban gaya.",
)

CASTLE = (
    "{san}. Raja safe, rook ready.",
    "{side} ne {san} karke badshah ko side me park kar diya.",
    "{san} — king ko ghar, rook ko road.",
    "{san}. Ab raja chain se, pieces kaam pe.",
)

BLUNDER = (
    "{san}?! Arre bhau, ye kya kar diya!",
    "{san}?! Baap re, yaha haath fisal gaya.",
    "{san}?! Arey yaar, opponent ko free ka gift mil gaya.",
    "{san}?! Kya jhol kar diya re.",
    "{san}?! Ye wali chaal mehengi pad sakti hai.",
    "{san}?! Haan bhai... ab damage control.",
    "{san}?! Engine ne seedha kaan pakad liya.",
)

MISTAKE = (
    "{san}... hmm, yaha thoda better sambhal sakte the.",
    "{san} — chhoti si slip, par position ne notice kar li.",
    "{san}? Idea hai, par timing thodi off lag rahi.",
    "{san}... ek tempo halka sa chala gaya.",
    "{san}; saamne wale ko thoda free ka saans mil gaya.",
)

BEST = (
    "{san}! Haan bhau, ye baat hai.",
    "{san}! Timing ekdum sahi.",
    "{san} — dikhne me seedha, kaam me tez.",
    "{san}! Chaal me calculation ki smell aa rahi hai.",
    "{san} — yahi move position ko suit karta hai.",
    "{san}! Nautanki kam, kaam zyada.",
)

STRONG = (
    "{san}! Oho, gear badla.",
    "{san}! Yaha se pressure sach me badh raha hai.",
    "{san} — ab game thoda tez hoga.",
    "{san}! Timing pakdi gayi.",
)

RETREAT = (
    "{san} — peeche gaya hai, surrender nahi.",
    "{san}; brake lagaya hai, gaadi band nahi.",
    "{san} — piece ko sambhal ke wapas kheench liya.",
    "{san}; kabhi do kadam peeche hi smartness hoti hai.",
)

ENDGAME = (
    "{san}. Ab king bhi proper mohra hai.",
    "{san} — endgame me yeh chhota step bhi bada hota hai.",
    "{san}; ab timing ka khel hai bhau.",
    "{san}. Board patla hai, har square ka hisaab hai.",
    "{san} — ab pawns aur king sab bolenge.",
)


# ============================================================================
# CLASS
# ============================================================================

class HumanCommentator:
    def __init__(self, seed: int = 360, history_size: int = 32):
        self.rng = random.Random(seed)
        self.history: list[str] = []
        self.history_size = history_size
        self.move_index = 0

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def comment(
        self,
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
        engine: Optional[EngineSnapshot] = None,
        recent_sans: tuple[str, ...] = (),
    ) -> Commentary:
        self.move_index += 1
        engine = engine or EngineSnapshot()

        f = self._facts(before, move, after, engine, recent_sans)

        main = self._make_main(f)
        main = self._maybe_add_context(f, main)
        main = self._clean(main)

        # Never allow exact recent duplication.
        if main in self.history[-8:]:
            main = self._clean(
                self._join(main, self._pick(SMALL_ASIDES))
            )

        self.history.append(main)
        self.history = self.history[-self.history_size:]

        return Commentary(
            commentary=main,
            plan=self._make_plan(f),
            threat=self._make_threat(f),
            watch=self._make_watch(f),
            tags=tuple(self._tags(f)),
        )

    # ------------------------------------------------------------------
    # facts
    # ------------------------------------------------------------------

    def _facts(
        self,
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
        engine: EngineSnapshot,
        recent_sans: tuple[str, ...],
    ) -> dict:
        color = before.turn
        san = before.san(move)
        piece = before.piece_at(move.from_square)

        captured = before.piece_at(move.to_square)
        if before.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not color)

        swing = engine.mover_swing(color)

        return {
            "color": color,
            "side": "White" if color == chess.WHITE else "Black",
            "san": san,
            "piece": self._piece_name(piece),
            "to_sq": chess.square_name(move.to_square),
            "captured": self._piece_name(captured) or "piece",
            "captured_value": self._value(captured),
            "is_capture": before.is_capture(move),
            "is_check": before.gives_check(move),
            "is_mate": before.gives_check(move) and after.is_checkmate(),
            "is_castle": before.is_castling(move),
            "is_promotion": move.promotion is not None,
            "development": self._development(before, move),
            "center": self._center(move),
            "pawn_break": self._pawn_break(before, move),
            "retreat": self._retreat(before, move),
            "swing": swing,
            "best": (
                engine.best_move_before is not None
                and engine.best_move_before == move
            ),
            "next_move": self._first(engine.pv_after_san),
            "next_reply": self._second(engine.pv_after_san),
            "phase": self._phase(after),
            "attacks_queen": self._attacks_type(after, move.to_square, color, chess.QUEEN),
            "attacks_rook": self._attacks_type(after, move.to_square, color, chess.ROOK),
            "fork": tuple(self._fork(after, move.to_square, color)),
            "hanging_enemy": self._hanging_enemy(after, color),
            "repeat": self._repeatish(move, recent_sans),
            "open_files": tuple(self._open_files(after)),
            "passed_pawns": tuple(self._passed_pawns(after, color)),
            "undeveloped": tuple(self._undeveloped(after, color)),
            "enemy_king_in_check": after.is_check() and after.turn != color,
        }

    # ------------------------------------------------------------------
    # main voice selection
    # ------------------------------------------------------------------

    def _make_main(self, f: dict) -> str:
        if f["is_mate"]:
            return self._pick(
                MATE,
                san=f["san"],
            )

        if f["is_promotion"]:
            return self._pick(PROMOTION, san=f["san"])

        if f["swing"] is not None and f["swing"] <= -180:
            return self._pick(BLUNDER, san=f["san"])

        if f["is_check"]:
            return self._pick(
                CHECK,
                side=f["side"],
                san=f["san"],
                opener=self._opener(),
            )

        if f["fork"]:
            targets = ", ".join(f["fork"][:2])
            return self._pick(
                (
                    "{san}! Ek piece, do bade target — {targets}.",
                    "{san}! Bhau, do jagah ek saath tension.",
                    "{san}; fork ka scene khol diya.",
                    "{san}! Ek teer me do nishane.",
                ),
                san=f["san"],
                targets=targets,
            )

        if f["attacks_queen"]:
            return self._pick(
                (
                    "{san}! Queen ko bhi chain nahi.",
                    "{san} — upar se queen pe tempo.",
                    "{san}! Queen ko ab address badalna padega.",
                ),
                san=f["san"],
            )

        if f["attacks_rook"]:
            return self._pick(
                (
                    "{san}! Rook ko ab zara sambhalna padega.",
                    "{san} — rook pe bhi nazar aa gayi.",
                ),
                san=f["san"],
            )

        if f["swing"] is not None and f["swing"] <= -70:
            return self._pick(MISTAKE, san=f["san"])

        if f["is_castle"]:
            return self._pick(CASTLE, side=f["side"], san=f["san"])

        if f["is_capture"] and f["captured_value"] >= 5:
            return self._pick(
                BIG_CAPTURE,
                san=f["san"],
                opener=self._opener(),
            )

        if f["is_capture"]:
            return self._pick(
                CAPTURE,
                side=f["side"],
                san=f["san"],
                captured=f["captured"],
                opener=self._opener(),
            )

        if f["best"] and (f["swing"] is None or f["swing"] >= 15):
            return self._pick(BEST, san=f["san"])

        if f["swing"] is not None and f["swing"] >= 100:
            return self._pick(STRONG, san=f["san"])

        if f["phase"] == "endgame" and self.rng.random() < 0.36:
            return self._pick(ENDGAME, san=f["san"])

        if f["pawn_break"]:
            return self._pick(PAWN_BREAK, side=f["side"], san=f["san"])

        if f["development"]:
            return self._pick(
                DEVELOPMENT,
                side=f["side"],
                san=f["san"],
                piece=f["piece"],
                to_sq=f["to_sq"],
            )

        if f["retreat"]:
            return self._pick(RETREAT, san=f["san"])

        if f["center"]:
            return self._pick(CENTER, side=f["side"], san=f["san"])

        return self._normal(f)

    def _normal(self, f: dict) -> str:
        side = f["side"]

        mode = self.rng.randrange(7)

        if mode == 0:
            return self._pick(
                NORMAL,
                opener=self._opener(),
                san=f["san"],
                side=side,
                line=self._pick(NORMAL_LINES),
            )

        if mode == 1:
            return (
                f"{f['san']}... "
                f"{self._pick(FILLERS).capitalize()}, "
                f"{self._pick(NORMAL_LINES)}."
            )

        if mode == 2:
            return f"{f['san']}. {self._pick(QUIET_SMART)}"

        if mode == 3:
            return f"{self._pick(OPENERS).capitalize()}, {f['san']}! {self._pick(SMALL_ASIDES)}"

        if mode == 4:
            return f"{f['san']} — {self._pick(NORMAL_LINES)}. {self._pick(ORDINARY_ENDINGS)}"

        if mode == 5:
            return f"{side} ka {f['san']}. {self._pick(NORMAL_LINES)}, bas."

        return f"{f['san']}. {self._pick(NORMAL_LINES)}; {self._pick(ORDINARY_ENDINGS)}"

    def _maybe_add_context(self, f: dict, main: str) -> str:
        # Human commentators don't explain every detail. Only add context
        # when the move actually changed the story.
        p = 0.0

        if f["is_mate"] or f["is_promotion"]:
            p = 0.95
        elif f["swing"] is not None and abs(f["swing"]) >= 140:
            p = 0.70
        elif f["is_check"] or f["fork"]:
            p = 0.48
        elif f["is_capture"] and f["captured_value"] >= 5:
            p = 0.50
        elif f["phase"] == "endgame":
            p = 0.25
        elif f["next_move"] and f["best"]:
            p = 0.22

        if self.rng.random() > p:
            return main

        context = self._context_sentence(f)
        return self._join(main, context)

    def _context_sentence(self, f: dict) -> str:
        if f["is_mate"]:
            return self._pick(
                (
                    "Bas bhau, shutter gira.",
                    "Ab iske baad kya hi bolna.",
                    "Game band, chai chalu.",
                )
            )

        if f["is_promotion"]:
            return self._pick(
                (
                    "Pawn ka career successful raha.",
                    "Bhau, promotion ka paisa vasool.",
                    "Ab naya piece seedha hukam chalega.",
                )
            )

        if f["swing"] is not None and f["swing"] <= -180:
            return self._pick(
                (
                    "Ab damage control ka time.",
                    "Ye gift saamne wala ignore nahi karega.",
                    "Ab agla move bahut sambhal ke.",
                    "Position ne warning bell baja di.",
                )
            )

        if f["swing"] is not None and f["swing"] >= 140:
            return self._pick(
                (
                    "Wah, yaha timing pakdi gayi.",
                    "Ab position me pressure ka rang aa gaya.",
                    "Ye move sach me game ko thoda kheench raha hai.",
                    "Ab saamne wale ko accurate rehna padega.",
                )
            )

        if f["is_check"]:
            return self._pick(
                (
                    "Ab reply force hai.",
                    "King ko ab khud raasta dhoondhna hai.",
                    "Yaha ek tempo bhi mehenga hai.",
                )
            )

        if f["fork"]:
            return self._pick(
                (
                    "Dono targets ka jugaad ek saath mushkil hai.",
                    "Ab bachao-bachao wala phase.",
                )
            )

        if f["phase"] == "endgame":
            return self._pick(
                (
                    "Ab har square ka hisaab hai.",
                    "Endgame me yahi chhoti details badi banti hain.",
                    "Ab king ko bhi actively kaam karna padega.",
                )
            )

        if f["next_move"] and f["best"]:
            return self._pick(
                (
                    f"Ab {f['next_move']} ka idea dekhne layak hai.",
                    f"Aage {f['next_move']} ka setup ban sakta hai.",
                    f"Next me {f['next_move']} type pressure aa sakta hai.",
                )
            )

        return self._pick(ORDINARY_ENDINGS)

    # ------------------------------------------------------------------
    # structured fields (kept for future UI, not required for spoken text)
    # ------------------------------------------------------------------

    def _make_plan(self, f: dict) -> str:
        if f["is_mate"]:
            return "Game over."

        if f["is_promotion"]:
            return "Promoted piece ko active rakhna."

        if f["phase"] == "endgame":
            if f["passed_pawns"]:
                return f"Passed pawn {f['passed_pawns'][0]} ki timing."
            if f["open_files"]:
                return f"{f['open_files'][0]}-file par rook activity."

        if f["undeveloped"]:
            return f"{f['undeveloped'][0]} ko develop karna."

        if f["next_move"]:
            return f"{f['next_move']} ka practical idea."

        return "Pieces ko active aur coordinated rakhna."

    def _make_threat(self, f: dict) -> str:
        if f["is_mate"]:
            return "None."

        if f["is_check"]:
            return "Forced king reply."

        if f["fork"]:
            return "Fork targets."

        if f["attacks_queen"]:
            return "Queen attacked."

        if f["attacks_rook"]:
            return "Rook attacked."

        if f["hanging_enemy"]:
            return f"{f['hanging_enemy']} target."

        if f["next_move"]:
            return f"Watch {f['next_move']}."

        return "No immediate tactical threat detected."

    def _make_watch(self, f: dict) -> str:
        if f["is_promotion"]:
            return "Promotion/checking sequence."

        if f["phase"] == "endgame":
            return "King activity and pawn race."

        if f["is_check"]:
            return "King escape squares."

        if f["next_move"]:
            return f"Next engine idea: {f['next_move']}."

        return "Opponent's next tempo."

    # ------------------------------------------------------------------
    # board helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _development(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
            return False
        if board.fullmove_number > 16:
            return False
        homes = (
            {chess.B1, chess.G1, chess.C1, chess.F1}
            if piece.color == chess.WHITE
            else {chess.B8, chess.G8, chess.C8, chess.F8}
        )
        return move.from_square in homes

    @staticmethod
    def _center(move: chess.Move) -> bool:
        c = {
            chess.C4, chess.D4, chess.E4, chess.F4,
            chess.C5, chess.D5, chess.E5, chess.F5,
        }
        return move.from_square in c or move.to_square in c

    @staticmethod
    def _pawn_break(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None or piece.piece_type != chess.PAWN:
            return False
        return board.is_capture(move) or abs(
            chess.square_rank(move.to_square)
            - chess.square_rank(move.from_square)
        ) == 2

    @staticmethod
    def _retreat(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None or piece.piece_type == chess.PAWN:
            return False
        old_rank = chess.square_rank(move.from_square)
        new_rank = chess.square_rank(move.to_square)
        return new_rank < old_rank if piece.color == chess.WHITE else new_rank > old_rank

    @staticmethod
    def _attackers(
        board: chess.Board,
        square: chess.Square,
        color: chess.Color,
    ) -> list[chess.Piece]:
        return [
            board.piece_at(sq)
            for sq in board.attackers(color, square)
            if board.piece_at(sq) is not None
        ]

    @staticmethod
    def _attacks_type(
        board: chess.Board,
        square: chess.Square,
        color: chess.Color,
        piece_type: int,
    ) -> bool:
        return any(
            board.piece_at(sq)
            and board.piece_at(sq).color != color
            and board.piece_at(sq).piece_type == piece_type
            for sq in board.attacks(square)
        )

    @staticmethod
    def _fork(board: chess.Board, square: chess.Square, color: chess.Color) -> list[str]:
        vals = []
        for sq in board.attacks(square):
            p = board.piece_at(sq)
            if p is None or p.color == color:
                continue
            if p.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                vals.append(
                    (
                        HumanCommentator._value(p),
                        f"{HumanCommentator._piece_name(p)} on {chess.square_name(sq)}",
                    )
                )
        vals.sort(reverse=True)
        return [x[1] for x in vals[:2]] if len(vals) >= 2 else []

    @staticmethod
    def _hanging_enemy(board: chess.Board, color: chess.Color) -> Optional[str]:
        enemy = not color
        for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            for sq in board.pieces(pt, enemy):
                a = board.attackers(color, sq)
                d = board.attackers(enemy, sq)
                if a and len(a) > len(d):
                    return (
                        f"{HumanCommentator._piece_name(board.piece_at(sq))}"
                        f" on {chess.square_name(sq)}"
                    )
        return None

    @staticmethod
    def _open_files(board: chess.Board) -> list[str]:
        files = []
        for file_idx in range(8):
            if not any(
                board.piece_at(chess.square(file_idx, rank))
                and board.piece_at(chess.square(file_idx, rank)).piece_type == chess.PAWN
                for rank in range(8)
            ):
                files.append(chr(ord("a") + file_idx))
        return files

    @staticmethod
    def _passed_pawns(board: chess.Board, color: chess.Color) -> list[str]:
        result = []
        enemy = not color
        enemy_pawns = list(board.pieces(chess.PAWN, enemy))

        for sq in board.pieces(chess.PAWN, color):
            file_idx = chess.square_file(sq)
            blocked = {
                chess.square_file(e)
                for e in enemy_pawns
                if abs(chess.square_file(e) - file_idx) <= 1
            }
            if file_idx not in blocked:
                result.append(chess.square_name(sq))
        return result

    @staticmethod
    def _undeveloped(board: chess.Board, color: chess.Color) -> list[str]:
        result = []

        if color == chess.WHITE:
            knight_home = (chess.B1, chess.G1)
            bishop_home = (chess.C1, chess.F1)
        else:
            knight_home = (chess.B8, chess.G8)
            bishop_home = (chess.C8, chess.F8)

        if any(
            board.piece_at(sq)
            and board.piece_at(sq).piece_type == chess.KNIGHT
            for sq in knight_home
        ):
            result.append("knight")

        if any(
            board.piece_at(sq)
            and board.piece_at(sq).piece_type == chess.BISHOP
            for sq in bishop_home
        ):
            result.append("bishop")

        return result

    @staticmethod
    def _phase(board: chess.Board) -> str:
        queens = sum(
            len(board.pieces(chess.QUEEN, c))
            for c in (chess.WHITE, chess.BLACK)
        )
        rooks = sum(
            len(board.pieces(chess.ROOK, c))
            for c in (chess.WHITE, chess.BLACK)
        )
        minors = sum(
            len(board.pieces(pt, c))
            for pt in (chess.BISHOP, chess.KNIGHT)
            for c in (chess.WHITE, chess.BLACK)
        )

        if board.fullmove_number <= 14 and queens >= 2:
            return "opening"
        if queens == 0 and rooks <= 2 and minors <= 4:
            return "endgame"
        return "middlegame"

    @staticmethod
    def _repeatish(move: chess.Move, recent: tuple[str, ...]) -> bool:
        dst = chess.square_name(move.to_square)
        return sum(dst in x for x in recent[-8:]) >= 3

    @staticmethod
    def _piece_name(piece: Optional[chess.Piece]) -> str:
        if piece is None:
            return ""
        return {
            chess.PAWN: "pawn",
            chess.KNIGHT: "knight",
            chess.BISHOP: "bishop",
            chess.ROOK: "rook",
            chess.QUEEN: "queen",
            chess.KING: "king",
        }.get(piece.piece_type, "piece")

    @staticmethod
    def _value(piece: Optional[chess.Piece]) -> int:
        if piece is None:
            return 0
        return {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
            chess.KING: 100,
        }.get(piece.piece_type, 0)

    @staticmethod
    def _first(pv: str) -> str:
        return pv.split()[0] if pv else ""

    @staticmethod
    def _second(pv: str) -> str:
        parts = pv.split()
        return parts[1] if len(parts) > 1 else ""

    def _opener(self) -> str:
        return self._pick(OPENERS)

    def _join(self, a: str, b: str) -> str:
        if not a:
            return b
        if not b:
            return a
        return f"{a.rstrip()} {b.lstrip()}"

    def _pick(self, pool, **values) -> str:
        options = []
        for x in pool:
            try:
                y = x.format(**values)
            except (KeyError, IndexError):
                continue
            if y not in self.history[-10:]:
                options.append(y)

        if not options:
            options = [x.format(**values) for x in pool]

        return self.rng.choice(options)

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.split()).replace("..", ".").strip()

    @staticmethod
    def _tags(f: dict) -> list[str]:
        tags = []
        if f["is_mate"]:
            tags.append("MATE")
        if f["is_check"]:
            tags.append("CHECK")
        if f["is_capture"]:
            tags.append("CAPTURE")
        if f["is_promotion"]:
            tags.append("PROMOTION")
        if f["is_castle"]:
            tags.append("CASTLE")
        if f["fork"]:
            tags.append("FORK")
        if f["loss"] is not None:
            if f["loss"] <= -180:
                tags.append("BLUNDER")
            elif f["loss"] <= -70:
                tags.append("MISTAKE")
            elif f["loss"] >= 100:
                tags.append("STRONG")
        if f["best"]:
            tags.append("BEST")
        if f["phase"] == "endgame":
            tags.append("ENDGAME")
        return tags


MATE = (
    "{san}! Bas bhau, shutter gira.",
    "{san}! Arre baap re, game khatam.",
    "{san}! Parda gir gaya.",
    "{san}! Raja ki kahani yahin band.",
)


_default: Optional[HumanCommentator] = None


def make_commentary(
    before: chess.Board,
    move: chess.Move,
    after: chess.Board,
    engine_snapshot: Optional[EngineSnapshot] = None,
    recent_sans: tuple[str, ...] = (),
) -> Commentary:
    global _default
    if _default is None:
        _default = HumanCommentator()

    return _default.comment(
        before=before,
        move=move,
        after=after,
        engine=engine_snapshot,
        recent_sans=recent_sans,
    )
