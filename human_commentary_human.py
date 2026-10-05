"""
STREAMKIDA — HUMAN COMMENTARY ENGINE (LOCAL / NO AI)

Goal:
    Natural Indian/desi Roman-Hinglish live chess chatter.

This module:
    - never uses an LLM
    - never makes a chess decision
    - never pushes a move
    - only comments on an already-verified move

The language engine is intentionally built around sentence architectures
rather than random word stuffing. Context-specific phrase banks produce a
very large number of combinations while keeping grammar natural.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Optional

import chess


@dataclass(frozen=True)
class EngineSnapshot:
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
    tags: tuple[str, ...] = ()


# ============================================================================
# VOICE
# ============================================================================

# These are not filler words. They are chosen to make the rhythm sound like
# spoken chat rather than written chess prose.
OPENERS = (
    "Arre",
    "Arey",
    "Oho",
    "Aila",
    "Baap re",
    "Arey bhau",
    "Oho bhau",
    "Haan bhai",
    "Bhau",
    "Arey yaar",
    "Areee",
    "Kya baat",
    "Dekho bhai",
    "Suno bhau",
    "Aika",
    "Arre baba",
    "Ohoho",
    "Haay",
    "Bhau re",
    "Kya scene",
    "Ab dekho",
    "Hmmm",
    "Arey re",
    "Wah bhau",
    "Bhai",
    "Oyy",
    "Arre wah",
    "Abe nahi,",
    "Accha bhau,",
    "Chalo bhai,",
    "Kya mast",
    "Hmm bhai,",
    "Aree baba,",
    "Wah re,",
    "Arre sun,",
    "Bhau ji,",
    "Oho re,",
    "Kya jhol,",
    "Arey haan,",
    "Chal bhau,",
)

CASUAL_TAGS = (
    "bhau",
    "bhai",
    "yaar",
    "re",
    "baba",
    "boss",
)

PAUSE_WORDS = (
    "hmm",
    "accha",
    "haan",
    "dekho",
    "waise",
    "sach bolu",
    "arre",
    "ab",
    "theek",
    "haan bhai",
)

SOFT_ENDINGS = (
    "ab dekhte hain.",
    "ab reply interesting hoga.",
    "ab asli sawaal iska jawab hai.",
    "abhi game zinda hai.",
    "ab yaha aankh hataana mat.",
    "ab maza aayega.",
    "ab dekhna, kya counter nikalta hai.",
    "ab next move bata dega asli baat.",
    "abhi kuch fixed nahi hai.",
    "ab scene dheere-dheere garam ho raha hai.",
    "ab ek chhoti chook bhi mehengi ho sakti hai.",
    "ab position khud jawab maang rahi hai.",
    "abhi picture baaki hai.",
    "ab game ko lightly mat lena.",
    "ab dekh bhau, kiska dimaag tez chalta hai.",
)

LIGHT_JOKES = (
    "mohra attendance laga gaya.",
    "piece ko finally naukri mil gayi.",
    "ab ye tourist banke board pe nahi ghoomega.",
    "board pe hisaab-kitab shuru.",
    "ab kisi ki chai thandi hone wali hai.",
    "ye move dekh ke bishop bhi khush hoga.",
    "ab position ne muh khol diya.",
    "seedha move, lekin pet me calculation.",
    "ab zara dimaag ka attendance chahiye.",
    "ye piece ab free ka mehmaan nahi.",
    "board pe setting ho rahi hai.",
    "yeh wala scene baad me yaad rahega.",
    "ab overconfidence ka tax lag sakta hai.",
    "game ne halka sa masala daal diya.",
    "ab koi bhi free me tempo nahi dega.",
    "yeh chaal chup hai, par khaali nahi.",
    "position ne signal de diya.",
    "ab asli khel bacha hai.",
)


# ============================================================================
# SITUATION-SPECIFIC PHRASES
# ============================================================================

NORMAL = (
    "{opener}, {san}.",
    "{opener}, {san} aa gaya.",
    "{opener} {san} — haan, samajh me aa raha hai.",
    "{san}... {side} ne ab {verb}.",
    "{opener} {san}! Ab {side} {verb2}.",
    "{san} — {side} ne {verb}.",
    "{opener}... {san}. {side} ka plan ab thoda saaf dikh raha hai.",
    "{san}. Dekho bhai, {side} {verb3}.",
    "{opener} {san}; move simple hai, idea simple nahi.",
)

DEVELOP = (
    "{side} ne {san} se {piece} ko seedha kaam pe laga diya.",
    "{san} — {piece} ab spectator nahi raha.",
    "{side} ka {san}; development bhi, active square bhi.",
    "{piece} ko {to_sq} pe bithaya, ab board pe duty karega.",
    "{san} se ek aur piece game me proper entry le raha hai.",
    "{side} ne {san} karke piece ko hawa me nahi, kaam me daala.",
    "{san}; chalo, mohre ko ghar se bahar nikaal hi diya.",
    "{side} ne {piece} ko {to_sq} pe rakh ke pieces ko jodne ki shuruaat ki.",
)

CENTER = (
    "{san}! Beech ka maidan chhodne ka mood nahi hai.",
    "{side} ka {san}; center pe seedha haq jata diya.",
    "{san} — center me kursi kheench ke baith gaye.",
    "{side} ne {san} se beech ka pressure aur badha diya.",
    "{san}; yaha center control ki asli tug-of-war shuru.",
    "{side} ka {san} center ko khali haath nahi jaane de raha.",
    "{san}! Beech me jagah ke liye full bargaining chal rahi hai.",
)

PAWN_BREAK = (
    "{san}! Pawn se seedha darwaza dhakka diya.",
    "{side} ka {san}; structure ko hilane ka button daba diya.",
    "{san} — pawn aage, ab peeche ke pieces ko kaam dikhana padega.",
    "{side} ne {san} se line todne ki soch dikha di.",
    "{san}; ye sirf pawn push nahi, position ko kholne ka signal hai.",
    "{side} ka {san} — ab space bhi milega aur tension bhi.",
)

CAPTURE = (
    "{san}! {side} ne {captured} ko board se hata diya.",
    "{side} ka {san}; seedha hisaab-kitab.",
    "{san} karke samaan uthaya gaya.",
    "{opener} {san}! Ek mohra kam, ab dekhte hain kiski calculation sahi baithti hai.",
    "{side} ne {captured} ko nikaal diya; exchange ka bill baad me milega.",
    "{san}; board thoda saaf hua hai.",
    "{san}! Accha, toh tension ko capture me badal diya.",
    "{side} ne {san} se position ka ek chapter band kar diya.",
)

BIG_CAPTURE = (
    "{san}! Arre bhau, itna bada samaan uth gaya.",
    "{san}! Rook gaya bhai, ab ye chhota exchange nahi.",
    "{san}! Material ka khaata zor se hil gaya.",
    "{san} — board pe dukaan saaf ho rahi hai.",
    "{opener} {san}! Ye capture dekh ke seedha hisaab lagana padega.",
)

CHECK = (
    "{san}! Raja ko seedha sawaal.",
    "{side} ka {san}; ab king ko jawab dena hi padega.",
    "{opener} {san}! King ko chain se baithne nahi diya.",
    "{san} — check bhi, tempo bhi.",
    "{side} ne {san} se conversation ekdum badal di.",
    "{san}! Raja ko zara uth-baith karwa diya.",
    "{opener} check aa gaya bhau — ab reply halka nahi chalega.",
    "{san}! Ab king ko khud bolna padega.",
)

MATE = (
    "{san}! Bas bhau, shutter gira.",
    "{san}! Arre baap re, kahani yahin khatam.",
    "{san}! Parda gir gaya.",
    "{san}! Iske baad commentary bhi chup.",
    "{san}! Raja ke paas ghar hi nahi bacha.",
    "{san}! Bas, game band.",
)

PROMOTION = (
    "{san}! Aila bhau, pawn ne promotion maar diya!",
    "{san}! Arey wah, pawn seedha malik ban gaya.",
    "{san}! Pawn ne naukri chhod ke bada aadmi ban liya.",
    "{san}! Itna door aa gaya tha, ab promotion toh banta tha.",
    "{san}! Bhau, ye pawn ab pawn mat bolna.",
    "{san}! Career complete, promotion mil gaya.",
)

CASTLE = (
    "{san} — king ko ghar, rook ko road.",
    "{side} ne {san} karke raja ko thoda chain de diya.",
    "{san}; king safety sorted, ab asli middlegame.",
    "{side} ka {san}; badshah parking me aa gaya.",
    "{san} — raja bach gaya, ab pieces ladenge.",
)

BLUNDER = (
    "{san}?! Arre bhau, yaha kya kar diya!",
    "{san}?! Baap re, ye toh seedha problem bula li.",
    "{san}?! Arey yaar, ye wali chaal halka pad gayi.",
    "{san}?! Kya jhol kar diya re.",
    "{san}?! Haan bhai... yaha haath fisal gaya.",
    "{san}?! Opponent ko itna free me khush nahi karna tha.",
    "{san}?! Arre baba, ye toh dard wali chaal hai.",
    "{san}?! Engine ko toh laddoo mil gaya hoga.",
    "{san}?! Iska bill ab bharna padega.",
)

MISTAKE = (
    "{san}... hmm, yaha thoda better sambhal sakte the.",
    "{san}... arey bhau, halka sa slip.",
    "{san} — idea samajh aa raha hai, par execution thoda fisla.",
    "{san}? Chhoti si chook, par position ne pakad li.",
    "{san}... yaha ek tempo haath se nikal gaya.",
    "{san}; opponent ko thoda free ka saans mil gaya.",
)

BEST = (
    "{san}! Haan bhau, timing mast hai.",
    "{san}! Ye move quietly kaam karta hai.",
    "{san} — dikhne me seedha, kaam me tez.",
    "{san}! Isme calculation bhi hai aur sense bhi.",
    "{san} — yahi chaal position ko suit kar rahi hai.",
    "{san}! Arey wah, ye samajh me aaya.",
    "{san}; nautanki kam, kaam zyada.",
)

STRONG = (
    "{san}! Oho, gear badal diya.",
    "{san}! Ab position ne boost liya.",
    "{san}; yaha timing pakdi gayi.",
    "{san}! Chaal se pressure seedha badh gaya.",
    "{san}; ab game thoda aur tez hoga.",
)

RETREAT = (
    "{san} — peeche gaya hai, par surrender nahi.",
    "{san}; brake lagaya hai, gaadi band nahi ki.",
    "{san} — piece ko wapas kheench ke position ko sambhala.",
    "{san}; do kadam peeche, par idea aage ka hai.",
)

FORK = (
    "{san}! Ek teer, do nishane.",
    "{san}! Arey bhau, do bade targets ek saath.",
    "{san}; ab dono pieces ko bachane ka jugaad dekho.",
    "{san}! Piece ne overtime kar diya — do jagah kaam.",
)

PIN = (
    "{san}! Ye piece ab bandh ke rakha hai.",
    "{san}; pinned piece ki azaadi gayi.",
    "{san}! Oho, seedha pin ka pressure.",
    "{san} — ab is piece ko hilna bhi soch ke padega.",
)

DISCOVERED = (
    "{san}! Aage ka mohra hila aur peeche ki line khul gayi.",
    "{san}; ek move, do line kaam pe.",
    "{san}! Oho, hidden pressure bahar aa gaya.",
    "{san} — chhota move, par peeche ka raasta khol diya.",
)


# ============================================================================
# HUMAN REACTION / EMOTION
# ============================================================================

EXCITED = (
    "Ab aaya maza!",
    "Wah bhau!",
    "Ye dekh ke maza aa gaya.",
    "Ab game me mirchi pad gayi.",
    "Scene ab garam hai.",
    "Aila, ab kuch hone wala hai.",
    "Bhau, yaha se aankh mat hata.",
    "Ab game serious mode me.",
    "Wah re timing.",
)

SHOCK = (
    "Arre re re...",
    "Baap re...",
    "Ohoho...",
    "Areee yaar...",
    "Haan bhai... ye unexpected tha.",
    "Arre baba...",
    "Kya scene kar diya...",
    "Ye dekho bhau...",
)

TEASE = (
    "ab iska jawab dekhna.",
    "ab opponent ko samjhana padega.",
    "ab ye gift seedha wapas nahi jayega.",
    "ab saamne wala bhi hisaab karega.",
    "ab dekhna kaun pehle ghabrata hai.",
    "ab yaha hawa me move chalna allowed nahi.",
)

QUIET_SMART = (
    "Zyada shor nahi, par kaam ka move hai.",
    "Chaal shaant hai, idea tez.",
    "Dikh raha normal hai, lekin detail me baat hai.",
    "Yaha style se zyada timing matter karti hai.",
    "Isme koi hungama nahi, par logic solid hai.",
)


# ============================================================================
# CORE CLASS
# ============================================================================

class HumanCommentator:
    """
    A stateful spoken-style commentator.

    The speaker intentionally does NOT comment with an identical structure
    every move.  It chooses among several sentence architectures, then adds
    an optional human aside only when the situation warrants it.
    """

    def __init__(
        self,
        seed: int = 360,
        history_size: int = 40,
    ):
        self.rng = random.Random(seed)
        self.history_size = history_size
        self.history: list[str] = []
        self.move_index = 0

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

        f = self._analyze(before, move, after, engine, recent_sans)
        tags = self._tags(f)

        main = self._choose_main(f)
        if self._add_reaction(f):
            main = self._join(main, self._choose_reaction(f))

        main = self._clean(main)

        if main in self.history[-10:]:
            main = self._clean(
                self._join(main, self._pick(LIGHT_JOKES))
            )

        self.history.append(main)
        self.history = self.history[-self.history_size:]

        return Commentary(
            commentary=main,
            plan=self._plan(f),
            threat=self._threat(f),
            watch=self._watch(f),
            tags=tuple(tags),
        )

    # ------------------------------------------------------------------
    # Situation analysis
    # ------------------------------------------------------------------

    def _analyze(
        self,
        before: chess.Board,
        move: chess.Move,
        after: chess.Board,
        engine: EngineSnapshot,
        recent_sans: tuple[str, ...],
    ) -> dict:
        color = before.turn
        piece = before.piece_at(move.from_square)

        captured = before.piece_at(move.to_square)
        if before.is_en_passant(move):
            captured = chess.Piece(chess.PAWN, not color)

        loss = None
        if engine.eval_before_cp is not None and engine.eval_after_cp is not None:
            delta = engine.eval_after_cp - engine.eval_before_cp
            loss = delta if color == chess.WHITE else -delta

        attack_info = self._attack_info(after, move.to_square, color)

        return {
            "color": color,
            "side": "White" if color == chess.WHITE else "Black",
            "piece": self._piece_name(piece),
            "san": before.san(move),
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
            "loss": loss,
            "best": (
                engine.best_move_before is not None
                and engine.best_move_before == move
            ),
            "pv": engine.pv_san,
            "next_pv": self._first(engine.pv_san),
            "open_files": tuple(self._open_files(after)),
            "phase": self._phase(after),
            "attacks_queen": attack_info["queen"],
            "attacks_rook": attack_info["rook"],
            "attacks_piece": attack_info["piece"],
            "fork": tuple(self._fork(after, move.to_square, color)),
            "pin": self._has_pin(after, color),
            "discovered": self._discovered(before, move, color),
            "hanging_enemy": self._hanging_enemy(after, color),
            "repeat": self._repeatish(move, recent_sans),
            "undeveloped": tuple(self._undeveloped(after, color)),
        }

    def _choose_main(self, f: dict) -> str:
        if f["is_mate"]:
            return self._pick(MATE, san=f["san"])

        if f["is_promotion"]:
            return self._pick(PROMOTION, san=f["san"])

        if f["loss"] is not None and f["loss"] <= -180:
            return self._pick(
                BLUNDER,
                san=f["san"],
                opener=self._opener(),
            )

        if f["is_check"]:
            return self._pick(
                CHECK,
                side=f["side"],
                san=f["san"],
                opener=self._opener(),
            )

        if f["fork"]:
            return self._pick(FORK, san=f["san"])

        if f["pin"]:
            return self._pick(PIN, san=f["san"])

        if f["discovered"]:
            return self._pick(DISCOVERED, san=f["san"])

        if f["loss"] is not None and f["loss"] <= -70:
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

        if f["best"] and (f["loss"] is None or f["loss"] >= 20):
            return self._pick(BEST, san=f["san"])

        if f["loss"] is not None and f["loss"] >= 100:
            return self._pick(STRONG, san=f["san"])

        if f["pawn_break"]:
            return self._pick(PAWN_BREAK, side=f["side"], san=f["san"])

        if f["development"]:
            return self._pick(
                DEVELOP,
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
        # Several architectures so the feed doesn't become "Arre X, now Y"
        # every single move.
        side = f["side"]

        mode = self.rng.randrange(6)

        verbs = (
            "position ko dheere-dheere set kar raha hai",
            "apne pieces ko aur active kar raha hai",
            "opponent ke options ko thoda naap raha hai",
            "agla idea taiyar kar raha hai",
            "board pe apni jagah pakad raha hai",
            "abhi seedha pressure nahi, pehle setup kar raha hai",
            "position ko apne hisaab se mod raha hai",
            "counterplay ke liye jagah bana raha hai",
        )

        v2 = (
            "thoda space le raha hai",
            "pieces ko jodne ki soch raha hai",
            "counterplay ka darwaza khol raha hai",
            "opponent ko comfortable nahi hone de raha",
            "ab next tempo ke liye jagah bana raha hai",
        )

        if mode == 0:
            return self._pick(
                NORMAL,
                opener=self._opener(),
                san=f["san"],
                side=side,
                verb=self._pick(verbs),
                verb2=self._pick(v2),
                verb3=self._pick(verbs),
            )

        if mode == 1:
            return (
                f"{f['san']}... "
                f"{self._pick(PAUSE_WORDS).capitalize()}, "
                f"{side.lower()} {self._pick(verbs)}."
            )

        if mode == 2:
            return (
                f"{side} ka {f['san']}. "
                f"{self._pick(QUIET_SMART)}"
            )

        if mode == 3:
            return (
                f"{self._pick(OPENERS)}, {f['san']}! "
                f"{self._pick(LIGHT_JOKES)}"
            )

        if mode == 4:
            return (
                f"{f['san']} — {self._pick(verbs)}. "
                f"{self._pick(SOFT_ENDINGS)}"
            )

        return (
            f"{f['san']}. "
            f"{self._pick(QUIET_SMART)} "
            f"{self._pick(SOFT_ENDINGS)}"
        )

    # ------------------------------------------------------------------
    # Human reaction
    # ------------------------------------------------------------------

    def _add_reaction(self, f: dict) -> bool:
        p = 0.18

        if f["is_mate"] or f["is_promotion"]:
            p = 0.85
        elif f["is_check"] or f["fork"]:
            p = 0.48
        elif f["loss"] is not None and f["loss"] <= -70:
            p = 0.62
        elif f["loss"] is not None and f["loss"] >= 100:
            p = 0.52
        elif f["is_capture"] and f["captured_value"] >= 5:
            p = 0.58
        elif f["phase"] == "endgame":
            p = 0.28

        return self.rng.random() < p

    def _choose_reaction(self, f: dict) -> str:
        if f["is_mate"] or f["is_promotion"]:
            return self._pick(EXCITED)

        if f["loss"] is not None and f["loss"] <= -70:
            return self._pick(
                SHOCK if f["loss"] <= -180 else TEASE
            )

        if f["is_check"] or f["fork"]:
            return self._pick(EXCITED)

        if f["loss"] is not None and f["loss"] >= 100:
            return self._pick(EXCITED)

        if f["is_capture"] and f["captured_value"] >= 5:
            return self._pick(EXCITED)

        return self._pick(MILD_REACTIONS)

    # ------------------------------------------------------------------
    # Plan / threat / watch
    # ------------------------------------------------------------------

    def _plan(self, f: dict) -> str:
        if f["is_mate"]:
            return "Bas bhau, kaam khatam."

        if f["is_promotion"]:
            return "Ab promoted piece ko active karna aur checks/king safety sambhalna main kaam hai."

        if f["phase"] == "endgame":
            if f["open_files"]:
                return f"Ab {f['open_files'][0]}-file pe rook activity aur king coordination pe focus."
            return "Ab king ko active rakhna aur pawn timing sahi pakadna sabse important hai."

        if f["undeveloped"]:
            return f"Agla natural kaam: {f['undeveloped'][0]} ko game me lana."

        if f["next_pv"]:
            return self._pick(
                (
                    f"Ab {f['next_pv']} jaisa idea dekhne layak hai.",
                    f"Agla pressure {f['next_pv']} ke around aa sakta hai.",
                    f"{f['next_pv']} wala setup nazar me rakhna.",
                    f"Aage {f['next_pv']} practical direction lag rahi hai.",
                )
            )

        if f["open_files"]:
            return f"Khuli {f['open_files'][0]}-file ko use karna natural plan hai."

        return self._pick(
            (
                "Ab pieces ko active rakhna aur free counterplay nahi dena.",
                "Aage opponent ka agla tempo dekh ke position ko adjust karna hai.",
                "Zyada jaldi nahi; pehle pieces ki coordination.",
                "Ab pressure ko maintain karke sahi moment ka wait karna hai.",
            )
        )

    def _threat(self, f: dict) -> str:
        if f["is_mate"]:
            return "Game khatam."

        if f["is_check"]:
            return "King ko forced reply dena hai."

        if f["fork"]:
            return "Fork ke targets me se kuch bachana padega."

        if f["attacks_queen"]:
            return "Queen pe tempo aa gaya."

        if f["attacks_rook"]:
            return "Rook ko ab safe square dekhna padega."

        if f["hanging_enemy"]:
            return f"{f['hanging_enemy']} par tactical nazar."

        if f["next_pv"]:
            return f"{f['next_pv']} ka idea agla pressure bana sakta hai."

        if f["pawn_break"]:
            return "Structure khul sakta hai; uske peeche ki pieces important hongi."

        return "Immediate knockout nahi, par accurate rehna zaroori hai."

    def _watch(self, f: dict) -> str:
        if f["is_promotion"]:
            return "Promotion square aur checking sequence."

        if f["phase"] == "endgame":
            return "King activity aur pawn race."

        if f["is_check"]:
            return "King ke escape squares aur loose pieces."

        if f["open_files"]:
            return f"{f['open_files'][0]}-file pe rook activity."

        if f["attacks_queen"]:
            return "Queen ka next safe square."

        return "Opponent ka next tempo."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _opener(self) -> str:
        # Never return an empty opener here because some sentence templates
        # intentionally include the comma after the opener.
        return self._pick(OPENERS)

    def _join(self, a: str, b: str) -> str:
        if not a:
            return b
        if not b:
            return a
        return f"{a.strip()} {b.strip()}"

    def _clean(self, text: str) -> str:
        text = " ".join(text.split())
        text = text.replace(" ,", ",").replace(" .", ".")
        text = text.replace("..", ".")
        return text.strip()

    def _pick(self, pool, **values) -> str:
        candidates = []
        for x in pool:
            try:
                y = x.format(**values)
            except (KeyError, IndexError):
                continue
            if y not in self.history[-10:]:
                candidates.append(y)

        if not candidates:
            candidates = [
                x.format(**values)
                for x in pool
            ]

        return self.rng.choice(candidates) if candidates else ""

    @staticmethod
    def _first(pv: str) -> str:
        return pv.split()[0] if pv else ""

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
        center = {
            chess.C4, chess.D4, chess.E4, chess.F4,
            chess.C5, chess.D5, chess.E5, chess.F5,
        }
        return move.from_square in center or move.to_square in center

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
        old = chess.square_rank(move.from_square)
        new = chess.square_rank(move.to_square)
        return new < old if piece.color == chess.WHITE else new > old

    @staticmethod
    def _attack_info(
        board: chess.Board,
        square: chess.Square,
        color: chess.Color,
    ) -> dict:
        out = {"queen": False, "rook": False, "piece": None}
        for sq in board.attacks(square):
            p = board.piece_at(sq)
            if p is None or p.color == color or p.piece_type == chess.KING:
                continue
            if p.piece_type == chess.QUEEN:
                out["queen"] = True
            elif p.piece_type == chess.ROOK:
                out["rook"] = True
            elif out["piece"] is None:
                out["piece"] = HumanCommentator._piece_name(p)
        return out

    @staticmethod
    def _fork(
        board: chess.Board,
        square: chess.Square,
        color: chess.Color,
    ) -> list[str]:
        targets = []
        for sq in board.attacks(square):
            p = board.piece_at(sq)
            if p is None or p.color == color:
                continue
            if p.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                targets.append(
                    (
                        HumanCommentator._value(p),
                        f"{HumanCommentator._piece_name(p)} on {chess.square_name(sq)}",
                    )
                )
        targets.sort(reverse=True)
        return [x[1] for x in targets[:2]] if len(targets) >= 2 else []

    @staticmethod
    def _has_pin(board: chess.Board, color: chess.Color) -> bool:
        enemy = not color
        for piece_type in (
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
        ):
            for sq in board.pieces(piece_type, enemy):
                try:
                    if board.is_pinned(enemy, sq):
                        return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _discovered(
        before: chess.Board,
        move: chess.Move,
        color: chess.Color,
    ) -> bool:
        # Conservative test: moving piece leaves a square between a friendly
        # slider and an enemy major/king along a ray.
        for sq in (
            before.pieces(chess.ROOK, color)
            | before.pieces(chess.BISHOP, color)
            | before.pieces(chess.QUEEN, color)
        ):
            if sq == move.from_square:
                continue

            between = before.attacks(sq)
            if move.from_square not in between:
                continue

            temp = before.copy()
            try:
                temp.push(move)
            except Exception:
                continue

            for target in temp.attacks(sq):
                victim = temp.piece_at(target)
                if victim and victim.color != color and victim.piece_type in (
                    chess.KING,
                    chess.QUEEN,
                    chess.ROOK,
                ):
                    return True
        return False

    @staticmethod
    def _hanging_enemy(
        board: chess.Board,
        color: chess.Color,
    ) -> Optional[str]:
        enemy = not color
        for pt in (
            chess.QUEEN,
            chess.ROOK,
            chess.BISHOP,
            chess.KNIGHT,
        ):
            for sq in board.pieces(pt, enemy):
                attackers = board.attackers(color, sq)
                defenders = board.attackers(enemy, sq)
                if attackers and len(attackers) > len(defenders):
                    return (
                        f"{HumanCommentator._piece_name(board.piece_at(sq))}"
                        f" on {chess.square_name(sq)}"
                    )
        return None

    @staticmethod
    def _open_files(board: chess.Board) -> list[str]:
        out = []
        for file_idx in range(8):
            if all(
                not (
                    board.piece_at(chess.square(file_idx, rank))
                    and board.piece_at(chess.square(file_idx, rank)).piece_type
                    == chess.PAWN
                )
                for rank in range(8)
            ):
                out.append(chr(ord("a") + file_idx))
        return out

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

        if board.fullmove_number <= 12 and queens >= 2:
            return "opening"
        if queens == 0 and rooks <= 2 and minors <= 4:
            return "endgame"
        return "middlegame"

    @staticmethod
    def _undeveloped(board: chess.Board, color: chess.Color) -> list[str]:
        out = []

        if color == chess.WHITE:
            knight_homes = (chess.B1, chess.G1)
            bishop_homes = (chess.C1, chess.F1)
        else:
            knight_homes = (chess.B8, chess.G8)
            bishop_homes = (chess.C8, chess.F8)

        if any(
            board.piece_at(sq)
            and board.piece_at(sq).piece_type == chess.KNIGHT
            for sq in knight_homes
        ):
            out.append("knight")

        if any(
            board.piece_at(sq)
            and board.piece_at(sq).piece_type == chess.BISHOP
            for sq in bishop_homes
        ):
            out.append("bishop")

        return out

    @staticmethod
    def _repeatish(move: chess.Move, recent: tuple[str, ...]) -> bool:
        dst = chess.square_name(move.to_square)
        return sum(dst in san for san in recent[-8:]) >= 3

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
        if f["pin"]:
            tags.append("PIN")
        if f["discovered"]:
            tags.append("DISCOVERED")
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

    @staticmethod
    def phrase_space_estimate() -> int:
        # Spoken templates + contextual banks.  This is a lower-bound estimate
        # because different situation branches use different banks.
        return (
            len(OPENERS)
            * len(NORMAL)
            * len(LIGHT_JOKES)
            * len(SOFT_ENDINGS)
            + len(DEVELOP) * len(EXCITED)
            + len(CAPTURE) * len(MILD_REACTIONS)
            + len(CHECK) * len(EXCITED)
            + len(BLUNDER) * len(SHOCK) * len(TEASE)
            + len(MISTAKE) * len(SHOCK)
            + len(PROMOTION) * len(EXCITED)
            + len(FORK) * len(EXCITED)
            + len(PIN) * len(EXCITED)
        )


# Extra mild reaction bank kept separate to avoid using strong emotion on
# every ordinary move.
MILD_REACTIONS = (
    "theek hai",
    "haan, ye sensible lag raha hai.",
    "hmm, ye idea samajh me aa raha hai.",
    "accha, ab picture thodi clear.",
    "haan bhai, ye ek kaam ki chaal hai.",
    "ab dekhna aage kya nikalta hai.",
    "yaha patience chahiye.",
    "scene abhi balanced hai.",
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


if __name__ == "__main__":
    print(
        "Estimated human-style phrase combinations:",
        HumanCommentator.phrase_space_estimate(),
    )
