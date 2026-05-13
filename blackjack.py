"""
utils/blackjack.py – Pure-Python blackjack logic (no Discord imports).

Provides the Deck, Hand, and GameState classes used by the games cog.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto


# ── Card representation ────────────────────────────────────────────────────────

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# Face value lookup (Aces handled separately)
RANK_VALUES: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11,
}


@dataclass
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def value(self) -> int:
        return RANK_VALUES[self.rank]


class Deck:
    """A standard 52-card deck that reshuffles when running low."""

    def __init__(self) -> None:
        self._cards: list[Card] = []
        self._build()

    def _build(self) -> None:
        self._cards = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self._cards)

    def draw(self) -> Card:
        if len(self._cards) < 10:
            self._build()
        return self._cards.pop()


# ── Hand helpers ───────────────────────────────────────────────────────────────

def hand_value(cards: list[Card]) -> int:
    """Calculate the best hand value, treating Aces as 1 if needed."""
    total = sum(c.value for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def cards_str(cards: list[Card]) -> str:
    return "  ".join(str(c) for c in cards)


# ── Game outcome ───────────────────────────────────────────────────────────────

class Outcome(Enum):
    PLAYER_WIN = auto()
    DEALER_WIN = auto()
    PUSH       = auto()
    BLACKJACK  = auto()   # natural blackjack (1.5× payout)
    BUST       = auto()   # player bust


# ── Game state ─────────────────────────────────────────────────────────────────

@dataclass
class BlackjackGame:
    bet: int
    player_cards: list[Card] = field(default_factory=list)
    dealer_cards: list[Card] = field(default_factory=list)
    deck: Deck = field(default_factory=Deck)
    doubled: bool = False

    def deal_initial(self) -> None:
        """Deal two cards each to player and dealer."""
        self.player_cards = [self.deck.draw(), self.deck.draw()]
        self.dealer_cards = [self.deck.draw(), self.deck.draw()]

    # ── Player actions ─────────────────────────────────────────────────────────

    def hit(self) -> Card:
        card = self.deck.draw()
        self.player_cards.append(card)
        return card

    def double_down(self, extra_bet: int) -> Card:
        """Double the bet, draw exactly one card, then stand."""
        self.bet += extra_bet
        self.doubled = True
        card = self.deck.draw()
        self.player_cards.append(card)
        return card

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def player_total(self) -> int:
        return hand_value(self.player_cards)

    @property
    def dealer_total(self) -> int:
        return hand_value(self.dealer_cards)

    @property
    def player_busted(self) -> bool:
        return self.player_total > 21

    @property
    def is_natural_blackjack(self) -> bool:
        return (
            len(self.player_cards) == 2
            and self.player_total == 21
            and not (len(self.dealer_cards) == 2 and self.dealer_total == 21)
        )

    # ── Dealer play-out ────────────────────────────────────────────────────────

    def play_dealer(self) -> None:
        """Dealer draws until reaching 17 or more (standard casino rules)."""
        while self.dealer_total < 17:
            self.dealer_cards.append(self.deck.draw())

    # ── Resolve ────────────────────────────────────────────────────────────────

    def resolve(self) -> tuple[Outcome, int]:
        """
        Play out the dealer hand and calculate outcome + net coin change.

        Returns (Outcome, coin_delta) where coin_delta is positive for wins.
        """
        if self.player_busted:
            return Outcome.BUST, -self.bet

        if self.is_natural_blackjack:
            payout = int(self.bet * 1.5)
            return Outcome.BLACKJACK, payout

        self.play_dealer()

        p = self.player_total
        d = self.dealer_total

        if d > 21 or p > d:
            return Outcome.PLAYER_WIN, self.bet
        elif p < d:
            return Outcome.DEALER_WIN, -self.bet
        else:
            return Outcome.PUSH, 0
