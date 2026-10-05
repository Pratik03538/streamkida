"""
STREAMKIDA - HUMAN COMMENTARY ENGINE
====================================

A fully local, deterministic chess commentator.

There is NO LLM, NO Gemini, NO Ollama, and NO network call here.

Authority:
    python-chess -> board truth / legality
    Stockfish    -> objective evaluation / PV
    this module  -> human-style commentary only

The module deliberately favors:
    - Roman Hinglish
    - light desi / gavran flavour
    - funny but chess-grounded reactions
    - tactical awareness
    - plans based on real board features
    - variation without repeating the same sentence pattern

It never selects or changes a chess move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Optional

import chess


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EngineSnapshot:
    """Objective engine context supplied by the caller."""

    eval_before_cp: Optional[int] = None
    eval_after_cp: Optional[int] = None
    best_move_before: Optional[chess.Move] = None
    best_move_after: Optional[chess.Move] = None
    pv_san: str = ""
    depth: int = 0

    @property
    def swing_white_cp(self) -> Optional[int]:
        if self.eval_before_cp is None or self.eval_after_cp is None:
            return None
        return self.eval_after_cp - self.eval_before_cp


@dataclass
class Commentary:
    commentary: str
    plan: str
    threat: str
    watch: str
    tags: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Stateful commentator
# ---------------------------------------------------------------------------

class HumanCommentator:
    """
    Stateful deterministic commentator.

    A local RNG is used only to vary phrasing. Chess facts always come from
    python-chess and the supplied Stockfish snapshot.
    """

    def __init__(self, seed: int = 360, max_history: int = 18):
        self.rng = random.Random(seed)
        self.max_history = max_history
        self.phrase_history: list[str] = []
        self.last_side: Optional[chess.Color] = None
        self.move_index = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def comment(
        self,
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
        engine: Optional[EngineSnapshot] = None,
        recent_sans: tuple[str, ...] = (),
    ) -> Commentary:
        """Generate commentary for one already-verified move."""

        self.move_index += 1
        engine = engine or EngineSnapshot()

        mover = before.turn
        san = before.san(move)

        facts = self._collect_facts(before, move, after, engine, recent_sans)
        tags = self._build_tags(facts)

        reaction = self._reaction_phrase(facts, mover)
        action = self._action_sentence(facts, san, mover)
        tactical = self._tactical_sentence(facts, mover)
        emotional = self._emotion_sentence(facts, mover)
        commentary = self._compose(reaction, action, tactical, emotional, facts)

        plan = self._plan_sentence(facts, after, engine)
        threat = self._threat_sentence(facts, after, engine)
        watch = self._watch_sentence(facts, after, engine)

        return Commentary(
            commentary=commentary,
            plan=plan,
            threat=threat,
            watch=watch,
            tags=tuple(tags),
        )

    # ------------------------------------------------------------------
    # Fact extraction
    # ------------------------------------------------------------------

    def _collect_facts(
        self,
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
        engine: EngineSnapshot,
        recent_sans: tuple[str, ...],
    ) -> dict:
        mover = before.turn
        piece = before.piece_at(move.from_square)
        captured = before.piece_at(move.to_square)

        if before.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not mover)

        swing_for_mover = None
        if engine.swing_white_cp is not None:
            swing_for_mover = (
                engine.swing_white_cp
                if mover == chess.WHITE
                else -engine.swing_white_cp
            )

        is_best = (
            engine.best_move_before is not None
            and engine.best_move_before == move
        )

        facts = {
            "mover": mover,
            "san": before.san(move),
            "piece": piece,
            "piece_name": self._piece_name(piece),
            "piece_letter": piece.symbol().upper() if piece else "",
            "from": move.from_square,
            "to": move.to_square,
            "from_name": chess.square_name(move.from_square),
            "to_name": chess.square_name(move.to_square),
            "captured": captured,
            "captured_name": self._piece_name(captured),
            "is_capture": before.is_capture(move),
            "is_en_passant": before.is_en_passant(move),
            "is_check": before.gives_check(move),
            "is_mate": before.gives_check(move) and after.is_checkmate(),
            "is_castle": before.is_castling(move),
            "is_promotion": move.promotion is not None,
            "promotion_name": self._promotion_name(move.promotion),
            "is_best": is_best,
            "engine_swing": swing_for_mover,
            "eval_before_cp": engine.eval_before_cp,
            "eval_after_cp": engine.eval_after_cp,
            "pv_san": engine.pv_san,
            "depth": engine.depth,
            "recent_sans": recent_sans,
            "phase": self._phase(after),
            "center_move": self._touches_center(move),
            "pawn_break": self._is_pawn_break(before, move),
            "development": self._is_development_move(before, move),
            "retreat": self._looks_like_retreat(before, move),
            "repetition_like": self._is_repeatish_move(move, recent_sans),
        }

        facts["captured_value"] = self._piece_value(captured)
        facts["mover_value"] = self._piece_value(piece)

        facts["fork_targets"] = self._fork_targets(after, move.to_square, mover)
        facts["checks_around"] = self._check_context(before, move, after)
        facts["pin_exists"] = self._creates_pin(after, move.to_square, mover)
        facts["discovered_attack"] = self._discovers_line_attack(before, move, mover)

        facts["hanging_enemy"] = self._find_hanging_enemy_piece(after, mover)
        facts["attacked_mover_piece"] = self._is_attacked_by_enemy(after, move.to_square, mover)

        facts["king_safety"] = self._king_safety(after, mover)
        facts["open_files"] = self._open_files(after)
        facts["passed_pawns"] = self._passed_pawns(after, mover)
        facts["undeveloped"] = self._undeveloped_minors(after, mover)

        facts["next_pv_move"] = self._first_pv_move(engine.pv_san)
        facts["eval_story"] = self._eval_story(swing_for_mover, is_best, facts)

        return facts

    def _build_tags(self, f: dict) -> list[str]:
        tags: list[str] = []

        if f["is_mate"]:
            tags.append("MATE")
        elif f["is_check"]:
            tags.append("CHECK")

        if f["is_promotion"]:
            tags.append("PROMOTION")
        if f["is_capture"]:
            tags.append("CAPTURE")
        if f["is_castle"]:
            tags.append("CASTLE")
        if f["pawn_break"]:
            tags.append("PAWN_BREAK")
        if f["development"]:
            tags.append("DEVELOPMENT")
        if f["center_move"]:
            tags.append("CENTER")
        if f["fork_targets"]:
            tags.append("FORK")
        if f["pin_exists"]:
            tags.append("PIN")
        if f["discovered_attack"]:
            tags.append("DISCOVERED")
        if f["hanging_enemy"] is not None:
            tags.append("HANGING")
        if f["attacked_mover_piece"]:
            tags.append("COUNTERATTACK")
        if f["engine_swing"] is not None:
            if f["engine_swing"] <= -200:
                tags.append("BLUNDER")
            elif f["engine_swing"] <= -80:
                tags.append("MISTAKE")
            elif f["engine_swing"] >= 140:
                tags.append("BIG_IMPROVEMENT")
        if f["is_best"]:
            tags.append("BEST")
        if f["retreat"]:
            tags.append("RETREAT")
        if f["phase"] == "endgame":
            tags.append("ENDGAME")

        return tags

    # ------------------------------------------------------------------
    # Main commentary
    # ------------------------------------------------------------------

    def _reaction_phrase(self, f: dict, side: chess.Color) -> str:
        if f["is_mate"]:
            pool = [
                "Areee bhau, bas! Parda gir gaya.",
                "Arre baap re, yahi pe kahani khatam!",
                "Kya jhol pakda aur seedha mat!",
                "Bhau, ab bacha hi kya hai?",
            ]
        elif f["is_promotion"]:
            pool = [
                "Arre wah, pawn ne naukri chhod ke bada aadmi ban liya!",
                "Aila bhau, promotion ka scene on!",
                "Bhau, ye pawn seedha malik ban gaya!",
            ]
        elif f["is_check"]:
            pool = [
                "Oho bhau, check ke saath seedha sawaal!",
                "Arey arey, raja ko zara hila diya!",
                "Wah, tempo ke saath check bhi!",
                "Bhau ne seedha king ko address kiya!",
            ]
        elif f["engine_swing"] is not None and f["engine_swing"] <= -200:
            pool = [
                "Arre bhau, yaha haath zara phisal gaya!",
                "Arey yaar, ye wali chaal jeb pe bhaari pad sakti hai.",
                "Oho, position se thoda paisa nikal gaya!",
                "Bhau, yaha engine ko khushi ho gayi hogi!",
            ]
        elif f["engine_swing"] is not None and f["engine_swing"] <= -80:
            pool = [
                "Arey bhau, zara sambhal ke!",
                "Hmmm, yaha thodi si chook nazar aa rahi hai.",
                "Bhau, ye bilkul free ka tempo nahi tha.",
                "Oho, position ne halka sa daant diya.",
            ]
        elif f["fork_targets"]:
            pool = [
                "Aila bhau, ek chaal aur do nishane!",
                "Kya setting hai, do mohre ek saath line me!",
                "Bhau ne ek teer se do shikaar pakad liye!",
            ]
        elif f["pin_exists"]:
            pool = [
                "Oho, mohre ko pin pe bitha diya!",
                "Bhau ne seedha keel thok di position me!",
                "Arey, ye pressure chupchaap kaam karega.",
            ]
        elif f["is_castle"]:
            pool = [
                "Chalo bhau, badshah ko ab ghar mil gaya.",
                "Oho, king ko parking se andar le aaye.",
                "Bhau, ab raja thoda chain se saans lega.",
            ]
        elif f["is_capture"]:
            pool = [
                "Oho, kuch toh uthaya gaya!",
                "Bhau ne samaan halka kar diya.",
                "Arey, board pe exchange ka hisaab khul gaya.",
                "Chalo, ek mohra kam.",
            ]
        elif f["pawn_break"]:
            pool = [
                "Oho, pawn se darwaza todne nikle hain!",
                "Bhau ne center me laat maar di.",
                "Arey, pawn break se position ko hila diya.",
            ]
        elif f["development"]:
            pool = [
                "Bilkul, mohre ko duty pe bhej diya.",
                "Oho, development ka kaam chalu.",
                "Bhau, piece ko ghuma ke board pe kaam diya.",
            ]
        elif f["retreat"]:
            pool = [
                "Arey, mohra do kadam peeche—kuch toh socha hai.",
                "Bhau ne brake laga diya, aur wajah hogi.",
                "Oho, retreat hai par surrender nahi.",
            ]
        elif f["center_move"]:
            pool = [
                "Center me seedha dabav badh raha hai.",
                "Bhau, beech ka maidan chhodega nahi!",
                "Oho, center pe apni kursi jama di.",
            ]
        else:
            pool = [
                "Chal bhau, game ko aage dhakelte hain.",
                "Theek hai bhau, ab position ka asli kaam shuru.",
                "Oho, ek aur piece board pe apna haq jata raha hai.",
                "Bhau ne chaal chal di, ab jawab dekhte hain.",
            ]

        return self._pick(pool)

    def _action_sentence(self, f: dict, san: str, side: chess.Color) -> str:
        actor = "White" if side == chess.WHITE else "Black"

        if f["is_mate"]:
            return f"{actor} ka {san} seedha final notice ban gaya."

        if f["is_promotion"]:
            return f"{actor} ka {san}—pawn ne promotion maar ke pura hisaab palat diya."

        if f["is_castle"]:
            return f"{actor} ne {san} se king ko safe karke pieces ko kaam pe rakha."

        if f["is_capture"]:
            cap = f["captured_name"] or "piece"
            if f["is_en_passant"]:
                return f"{actor} ne {san} se en-passant wala jugaad kar diya."
            return f"{actor} ne {san} se {cap} hata diya; exchange ka balance ab important hai."

        if f["pawn_break"]:
            return f"{actor} ka {san} pawn structure ko jhatka dekar lines kholne ka signal hai."

        if f["development"]:
            return f"{actor} ka {san} piece ko active square de raha hai aur development ko speed milti hai."

        if f["retreat"]:
            return f"{actor} ka {san} seedha attack nahi, pehle piece ko sahi jagah bithane ka kaam hai."

        if f["center_move"]:
            return f"{actor} ka {san} center par grip ko aur tight karta hai."

        return f"{actor} ka {san} position ko dheere-dheere shape de raha hai."

    def _tactical_sentence(self, f: dict, side: chess.Color) -> str:
        if f["is_mate"]:
            return "Ab counterplay ka sawaal hi khatam."

        if f["fork_targets"]:
            names = ", ".join(f["fork_targets"][:2])
            return f"Sabse mazedaar baat: ek hi piece se {names} par pressure aa gaya hai."

        if f["pin_exists"]:
            return "Pinned piece ab freely hil nahi sakta, isliye pressure practical bhi hai."

        if f["discovered_attack"]:
            return "Move ke saath peeche ki line bhi khul gayi—yahi chhota sa detail bade kaam ka ho sakta hai."

        if f["hanging_enemy"] is not None:
            return f"{f['hanging_enemy']} par dhyan dena padega; woh ab awkwardly defended lag raha hai."

        if f["attacked_mover_piece"]:
            return "Maujood pressure ke saath opponent ka tempo bhi aa sakta hai, toh next reply ko halka mat lena."

        if f["is_check"]:
            return "Check ne reply ko force kar diya, isliye initiative filhaal isi side ke paas hai."

        if f["engine_swing"] is not None and f["engine_swing"] >= 140:
            return "Engine swing bhi isi move ko support kar raha hai—sirf style nahi, position bhi saath de rahi hai."

        if f["engine_swing"] is not None and f["engine_swing"] <= -200:
            return "Yaha tactical punishment ka chance badh gaya hai; next move ka defense bahut important hai."

        return ""

    def _emotion_sentence(self, f: dict, side: chess.Color) -> str:
        if f["is_mate"]:
            return self._pick([
                "Ab toh chai bhi thandi ho gayi.",
                "Bhau, file band karo.",
                "King ne resignation de diya, bas.",
            ])

        if f["is_promotion"]:
            return self._pick([
                "Ye wala scene dekh ke commentator ka BP bhi badhta hai!",
                "Promotion ke saath table pe masala full.",
                "Bhau, ab game ne rang badal diya.",
            ])

        if f["engine_swing"] is not None and f["engine_swing"] >= 140:
            return self._pick([
                "Yeh chaal dekh ke maza aaya.",
                "Bhau, yaha timing mast hai.",
                "Ye move quietly strong hai, nautanki kam, kaam zyada.",
            ])

        if f["engine_swing"] is not None and f["engine_swing"] <= -200:
            return self._pick([
                "Ab agla response dekhna asli tamasha hai.",
                "Position ab mazaak nahi kar rahi.",
                "Bhau, yaha se damage control ka kaam hai.",
            ])

        return self._pick([
            "Abhi game mast balance pe chal raha hai.",
            "Aage ka plan zyada interesting hone wala hai.",
            "Yaha patience ka test hai.",
            "",
        ])

    def _compose(
        self,
        reaction: str,
        action: str,
        tactical: str,
        emotional: str,
        f: dict,
    ) -> str:
        parts = [reaction, action]

        if tactical and self.rng.random() < 0.78:
            parts.append(tactical)

        if emotional and self.rng.random() < 0.62:
            parts.append(emotional)

        # Keep it punchy.
        text = " ".join(p.strip() for p in parts if p.strip())
        text = self._dedupe_spaces(text)

        # Avoid near-identical sentence chains.
        self.phrase_history.append(text)
        if len(self.phrase_history) > self.max_history:
            self.phrase_history.pop(0)

        return text

    # ------------------------------------------------------------------
    # Plan / threat / watch
    # ------------------------------------------------------------------

    def _plan_sentence(
        self,
        f: dict,
        after: chess.Board,
        engine: EngineSnapshot,
    ) -> str:
        side = f["mover"]

        if f["is_mate"]:
            return "Plan complete. Game khatam."

        if f["is_castle"] is False and after.has_kingside_castling_rights(side):
            king_sq = after.king(side)
            if king_sq is not None and chess.square_file(king_sq) == 4:
                return "Ab natural plan castling complete karke rook ko center/file pe laana hai."

        if f["undeveloped"]:
            name = f["undeveloped"][0]
            return f"Agla simple kaam: {name} ko develop karke pieces ko ek hi team me lana."

        if f["passed_pawns"]:
            return f"Passed pawn {f['passed_pawns'][0]} ko support dena endgame me bada plan ho sakta hai."

        if f["open_files"]:
            return f"Open file {f['open_files'][0]} par rook ko lana natural setup lagta hai."

        pv = self._first_pv_move(engine.pv_san)
        if pv:
            return f"Stockfish line me next practical idea {pv} dikhta hai—piece coordination ko wahi direction mil rahi hai."

        if f["phase"] == "endgame":
            return "Endgame me king activity aur pawn targets ab sabse bada mudda hain."

        if f["phase"] == "middlegame":
            return "Ab pieces ko active squares pe rakhna aur opponent ke counterplay ko control karna main kaam hai."

        return "Ab development complete karke position ko stable rakhna natural plan hai."

    def _threat_sentence(
        self,
        f: dict,
        after: chess.Board,
        engine: EngineSnapshot,
    ) -> str:
        if f["is_mate"]:
            return "Threat: none needed."

        if f["is_check"]:
            return "Threat: king ko ab forced reply dena padega."

        if f["fork_targets"]:
            return "Threat: forked pieces me se kam-se-kam ek ko bachana padega."

        if f["pin_exists"]:
            return "Threat: pinned piece ki limitation ko exploit kiya ja sakta hai."

        hanging = f["hanging_enemy"]
        if hanging:
            return f"Threat: {hanging} ko tactical target banaya ja sakta hai."

        pv = self._first_pv_move(engine.pv_san)
        if pv:
            return f"Next pressure: {pv} ka idea position me repeat ho sakta hai."

        if f["pawn_break"]:
            return "Threat: pawn break se lines khul sakti hain aur king/center par pressure badh sakta hai."

        return "Threat: immediate knockout nahi, par opponent ko accurate rehna padega."

    def _watch_sentence(
        self,
        f: dict,
        after: chess.Board,
        engine: EngineSnapshot,
    ) -> str:
        if f["is_promotion"]:
            return "Watch: promotion square aur rook checks—yaha ek tempo bhi mehenga hai."

        if f["phase"] == "endgame":
            if f["open_files"]:
                return f"Watch: {f['open_files'][0]} file par rook activity."
            return "Watch: king opposition aur passed-pawn timing."

        if f["is_check"]:
            return "Watch: checking sequence ke baad king ki shelter aur loose pieces."

        if f["is_capture"] and f["captured_value"] >= 3:
            return "Watch: exchange ke baad jo files/diagonals khuli hain, wahi asli story ho sakti hai."

        if f["pawn_break"]:
            return "Watch: pawn structure khulne ke baad kings kitne safe rehte hain."

        return "Watch: opponent ka next tempo—counterplay ko free me mat dena."

    # ------------------------------------------------------------------
    # Chess heuristics
    # ------------------------------------------------------------------

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
    def _piece_value(piece: Optional[chess.Piece]) -> int:
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
    def _promotion_name(piece_type: Optional[int]) -> str:
        return {
            chess.KNIGHT: "knight",
            chess.BISHOP: "bishop",
            chess.ROOK: "rook",
            chess.QUEEN: "queen",
        }.get(piece_type, "")

    @staticmethod
    def _touches_center(move: chess.Move) -> bool:
        center = {
            chess.D4, chess.E4, chess.D5, chess.E5,
            chess.C4, chess.F4, chess.C5, chess.F5,
        }
        return move.from_square in center or move.to_square in center

    @staticmethod
    def _phase(board: chess.Board) -> str:
        non_pawns = sum(
            len(board.pieces(pt, color))
            for pt in (
                chess.KNIGHT,
                chess.BISHOP,
                chess.ROOK,
                chess.QUEEN,
            )
            for color in (chess.WHITE, chess.BLACK)
        )
        queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(
            board.pieces(chess.QUEEN, chess.BLACK)
        )
        if board.fullmove_number <= 12 and non_pawns >= 10:
            return "opening"
        if non_pawns <= 6 or (queens == 0 and non_pawns <= 8):
            return "endgame"
        return "middlegame"

    @staticmethod
    def _is_development_move(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None or piece.piece_type not in (chess.KNIGHT, chess.BISHOP):
            return False

        if board.fullmove_number > 15:
            return False

        rank = chess.square_rank(move.to_square)
        if piece.color == chess.WHITE:
            return rank >= 2
        return rank <= 5

    @staticmethod
    def _is_pawn_break(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None or piece.piece_type != chess.PAWN:
            return False
        return chess.square_file(move.from_square) != chess.square_file(move.to_square) or (
            abs(chess.square_rank(move.to_square) - chess.square_rank(move.from_square)) == 2
        )

    @staticmethod
    def _looks_like_retreat(board: chess.Board, move: chess.Move) -> bool:
        piece = board.piece_at(move.from_square)
        if piece is None:
            return False
        old_rank = chess.square_rank(move.from_square)
        new_rank = chess.square_rank(move.to_square)
        if piece.color == chess.WHITE:
            return new_rank < old_rank
        return new_rank > old_rank

    @staticmethod
    def _is_repeatish_move(move: chess.Move, recent_sans: tuple[str, ...]) -> bool:
        try:
            dst = chess.square_name(move.to_square)
        except Exception:
            return False
        return sum(dst in san for san in recent_sans[-6:]) >= 2

    @staticmethod
    def _fork_targets(
        board: chess.Board,
        from_square: chess.Square,
        attacker_color: chess.Color,
    ) -> list[str]:
        piece = board.piece_at(from_square)
        if piece is None:
            return []

        targets: list[tuple[int, str]] = []
        for sq in board.attacks(from_square):
            target = board.piece_at(sq)
            if target is None or target.color == attacker_color:
                continue
            if target.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                targets.append((
                    HumanCommentator._piece_value(target),
                    f"{HumanCommentator._piece_name(target)} on {chess.square_name(sq)}",
                ))

        targets.sort(reverse=True)
        return [name for _, name in targets[:2]]

    @staticmethod
    def _check_context(
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
    ) -> str:
        if after.is_checkmate():
            return "mate"
        if after.is_check():
            return "check"
        return ""

    @staticmethod
    def _creates_pin(
        board: chess.Board,
        square: chess.Square,
        attacker_color: chess.Color,
    ) -> bool:
        enemy = not attacker_color
        for sq in board.pieces(chess.KNIGHT, enemy) | board.pieces(chess.BISHOP, enemy):
            try:
                if board.is_pinned(enemy, sq):
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _discovers_line_attack(
        before: chess.Board,
        move: chess.Move,
        mover: chess.Color,
    ) -> bool:
        # Conservative heuristic: moving off a bishop/rook/queen line that was
        # blocked by the moving piece can reveal a direct attack.
        piece = before.piece_at(move.from_square)
        if piece is None:
            return False

        slider_types = {
            chess.BISHOP: (chess.BISHOP, chess.QUEEN),
            chess.ROOK: (chess.ROOK, chess.QUEEN),
            chess.QUEEN: (chess.ROOK, chess.BISHOP, chess.QUEEN),
        }

        for target_sq in before.attacks(move.from_square):
            target = before.piece_at(target_sq)
            if target is None or target.color != mover:
                continue
            if target.piece_type not in slider_types:
                continue

            # After moving, if slider attacks an enemy king/queen/rook, mark it.
            for attacked in before.attacks(target_sq):
                victim = before.piece_at(attacked)
                if victim and victim.color != mover and victim.piece_type in (
                    chess.KING, chess.QUEEN, chess.ROOK
                ):
                    return True

        return False

    @staticmethod
    def _find_hanging_enemy_piece(
        board: chess.Board,
        mover: chess.Color,
    ) -> Optional[str]:
        enemy = not mover
        enemy_pieces = []
        for piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT):
            enemy_pieces.extend(board.pieces(piece_type, enemy))

        for sq in enemy_pieces:
            piece = board.piece_at(sq)
            if piece is None:
                continue
            attackers = board.attackers(mover, sq)
            defenders = board.attackers(enemy, sq)
            if attackers and len(attackers) > len(defenders):
                return f"{HumanCommentator._piece_name(piece)} on {chess.square_name(sq)}"

        return None

    @staticmethod
    def _is_attacked_by_enemy(
        board: chess.Board,
        square: chess.Square,
        mover: chess.Color,
    ) -> bool:
        return bool(board.attackers(not mover, square))

    @staticmethod
    def _king_safety(board: chess.Board, mover: chess.Color) -> str:
        king_sq = board.king(mover)
        if king_sq is None:
            return "unknown"
        attackers = board.attackers(not mover, king_sq)
        return "under_pressure" if attackers else "quiet"

    @staticmethod
    def _open_files(board: chess.Board) -> list[str]:
        result = []
        for file_idx in range(8):
            file_squares = [chess.square(file_idx, r) for r in range(8)]
            if not any(board.piece_at(sq) and board.piece_at(sq).piece_type == chess.PAWN for sq in file_squares):
                result.append(chr(ord("a") + file_idx))
        return result

    @staticmethod
    def _passed_pawns(board: chess.Board, color: chess.Color) -> list[str]:
        result = []
        pawns = board.pieces(chess.PAWN, color)
        enemy_pawns = board.pieces(chess.PAWN, not color)
        enemy_files = {chess.square_file(sq) for sq in enemy_pawns}

        for sq in pawns:
            f = chess.square_file(sq)
            if f not in enemy_files and f > 0 and f < 7:
                name = chess.square_name(sq)
                result.append(name)

        return result

    @staticmethod
    def _undeveloped_minors(
        board: chess.Board,
        color: chess.Color,
    ) -> list[str]:
        result = []
        for piece_type, label, home in (
            (chess.KNIGHT, "knight", (1, 6)),
            (chess.BISHOP, "bishop", (2, 5)),
        ):
            for sq in board.pieces(piece_type, color):
                if sq in home:
                    result.append(label)
        return result

    @staticmethod
    def _first_pv_move(pv_san: str) -> str:
        parts = pv_san.split()
        return parts[0] if parts else ""

    @staticmethod
    def _eval_story(
        swing_for_mover: Optional[int],
        is_best: bool,
        facts: dict,
    ) -> str:
        if facts["is_mate"]:
            return "mate"
        if swing_for_mover is None:
            return "unknown"
        if swing_for_mover >= 150 and is_best:
            return "excellent"
        if swing_for_mover >= 80:
            return "improving"
        if swing_for_mover <= -200:
            return "blunder"
        if swing_for_mover <= -80:
            return "mistake"
        return "stable"

    # ------------------------------------------------------------------
    # Phrasing helpers
    # ------------------------------------------------------------------

    def _pick(self, pool: list[str]) -> str:
        candidates = [p for p in pool if p and p not in self.phrase_history[-5:]]
        if not candidates:
            candidates = [p for p in pool if p]
        if not candidates:
            return ""
        return self.rng.choice(candidates)

    @staticmethod
    def _dedupe_spaces(text: str) -> str:
        return " ".join(text.split())


# ---------------------------------------------------------------------------
# Convenience function for minimal integration into main.py
# ---------------------------------------------------------------------------

_default_commentator: Optional[HumanCommentator] = None


def make_commentary(
    before: chess.Board,
    move: chess.Move,
    after: chess.Board,
    engine_snapshot: Optional[EngineSnapshot] = None,
    recent_sans: tuple[str, ...] = (),
) -> Commentary:
    """
    Minimal integration helper.

    This function has no side effects on the chess board and never calls an AI.
    """

    global _default_commentator
    if _default_commentator is None:
        _default_commentator = HumanCommentator()

    return _default_commentator.comment(
        before=before,
        move=move,
        after=after,
        engine=engine_snapshot,
        recent_sans=recent_sans,
    )
