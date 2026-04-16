"""Word lists for the telephone scenario.

Defines 40 base word lists with all unique words (no word appears in more than
one list) and 5 epoch orderings. Each epoch applies a fixed budget multiplier.
Callers select a single epoch via ``get_word_lists_for_epoch`` to get 40 word
lists with round numbers 1-40 and a constant multiplier.
"""

from typing import NamedTuple


class WordList(NamedTuple):
    """A word list assigned to a single round of the telephone game."""

    round_number: int
    items: list[str]


class _BaseList(NamedTuple):
    """Template for a word list, before round_number assignment."""

    items: list[str]


# 40 base word lists, sizes cycling 3, 4, 5, 5, 6, 7, 7, 8, 9, 17.
# Every word appears exactly once across all lists.
_BASE_LISTS: list[_BaseList] = [
    # --- cycle 1 (lists 0-9) ---
    # 0: 3 items
    _BaseList(items=["apple", "chair", "river"]),
    # 1: 4 items
    _BaseList(items=["hammer", "cloud", "penguin", "blanket"]),
    # 2: 5 items
    _BaseList(items=["guitar", "volcano", "sandwich", "telescope", "candle"]),
    # 3: 5 items
    _BaseList(items=["elephant", "microscope", "cinnamon", "lighthouse", "parachute"]),
    # 4: 6 items
    _BaseList(items=["dolphin", "compass", "lantern", "marble", "feather", "trumpet"]),
    # 5: 7 items
    _BaseList(
        items=["glacier", "pyramid", "anchor", "biscuit", "violin", "tornado", "sapphire"],
    ),
    # 6: 7 items
    _BaseList(
        items=["basket", "magnet", "pepper", "fountain", "curtain", "whistle", "diamond"],
    ),
    # 7: 8 items
    _BaseList(
        items=[
            "mushroom",
            "lanyard",
            "cabinet",
            "sparrow",
            "crystal",
            "balloon",
            "vinegar",
            "sextant",
        ],
    ),
    # 8: 9 items
    _BaseList(
        items=[
            "hammock",
            "ceramic",
            "blizzard",
            "octopus",
            "tambourine",
            "scarecrow",
            "nutmeg",
            "gazelle",
            "prism",
        ],
    ),
    # 9: 17 items
    _BaseList(
        items=[
            "avalanche",
            "bamboo",
            "chimney",
            "dungeon",
            "emerald",
            "falcon",
            "garlic",
            "horizon",
            "igloo",
            "jasmine",
            "kettle",
            "lemon",
            "mango",
            "napkin",
            "orchid",
            "pillow",
            "quartz",
        ],
    ),
    # --- cycle 2 (lists 10-19) ---
    # 10: 3 items
    _BaseList(items=["rocket", "saddle", "walnut"]),
    # 11: 4 items
    _BaseList(items=["beacon", "cobweb", "furnace", "gravel"]),
    # 12: 5 items
    _BaseList(items=["hermit", "javelin", "ketchup", "lobster", "mitten"]),
    # 13: 5 items
    _BaseList(items=["nectar", "oxygen", "plumber", "quarry", "raisin"]),
    # 14: 6 items
    _BaseList(items=["saffron", "thistle", "umbrella", "velvet", "waffle", "zenith"]),
    # 15: 7 items
    _BaseList(
        items=["apricot", "bonfire", "catapult", "dragonfly", "easel", "flamingo", "gondola"],
    ),
    # 16: 7 items
    _BaseList(
        items=["harness", "incense", "jigsaw", "kaleidoscope", "lattice", "meadow", "nozzle"],
    ),
    # 17: 8 items
    _BaseList(
        items=[
            "obelisk",
            "panther",
            "quicksand",
            "ratchet",
            "stallion",
            "thimble",
            "urchin",
            "venom",
        ],
    ),
    # 18: 9 items
    _BaseList(
        items=[
            "whirlpool",
            "xylophone",
            "yardstick",
            "zeppelin",
            "acorn",
            "bramble",
            "caribou",
            "daffodil",
            "eclipse",
        ],
    ),
    # 19: 17 items
    _BaseList(
        items=[
            "ferret",
            "goblet",
            "harpoon",
            "ivory",
            "juniper",
            "keystone",
            "lagoon",
            "masquerade",
            "nebula",
            "origami",
            "porcelain",
            "quintet",
            "riddle",
            "satchel",
            "tapestry",
            "utensil",
            "viaduct",
        ],
    ),
    # --- cycle 3 (lists 20-29) ---
    # 20: 3 items
    _BaseList(items=["wasp", "yeti", "zodiac"]),
    # 21: 4 items
    _BaseList(items=["asteroid", "barricade", "canyon", "dynamo"]),
    # 22: 5 items
    _BaseList(items=["ember", "fjord", "geyser", "hibiscus", "icicle"]),
    # 23: 5 items
    _BaseList(items=["jackal", "kayak", "locket", "monocle", "narwhal"]),
    # 24: 6 items
    _BaseList(items=["osprey", "palette", "quiver", "rampart", "scepter", "trellis"]),
    # 25: 7 items
    _BaseList(
        items=["unicorn", "vulture", "windmill", "xerox", "yachtsman", "zephyr", "albatross"],
    ),
    # 26: 7 items
    _BaseList(
        items=["bobsled", "cactus", "dagger", "espresso", "foxglove", "gargoyle", "hedgehog"],
    ),
    # 27: 8 items
    _BaseList(
        items=[
            "ibex",
            "junco",
            "koala",
            "lemur",
            "mongoose",
            "newt",
            "ocelot",
            "platypus",
        ],
    ),
    # 28: 9 items
    _BaseList(
        items=[
            "quetzal",
            "raccoon",
            "starfish",
            "toucan",
            "armadillo",
            "viper",
            "wombat",
            "xerus",
            "yak",
        ],
    ),
    # 29: 17 items
    _BaseList(
        items=[
            "abacus",
            "bellows",
            "chariot",
            "dominoes",
            "envelope",
            "firewood",
            "galleon",
            "handcart",
            "inkwell",
            "journal",
            "knapsack",
            "lariat",
            "mandolin",
            "nomad",
            "overcoat",
            "parchment",
            "rudder",
        ],
    ),
    # --- cycle 4 (lists 30-39) ---
    # 30: 3 items
    _BaseList(items=["sphinx", "trident", "unicycle"]),
    # 31: 4 items
    _BaseList(items=["velveteen", "whippet", "xeric", "yarrow"]),
    # 32: 5 items
    _BaseList(items=["zinnia", "aileron", "bulkhead", "capstan", "derrick"]),
    # 33: 5 items
    _BaseList(items=["eyelet", "flint", "gimbal", "hatchet", "ingot"]),
    # 34: 6 items
    _BaseList(items=["jackdaw", "kingpin", "lintel", "mortar", "nacelle", "oxbow"]),
    # 35: 7 items
    _BaseList(
        items=["pinnacle", "quartzite", "rigging", "schooner", "turret", "vestibule", "warbler"],
    ),
    # 36: 7 items
    _BaseList(
        items=["anemone", "barnacle", "cistern", "dragnet", "estuary", "flywheel", "grommet"],
    ),
    # 37: 8 items
    _BaseList(
        items=[
            "halyard",
            "impeller",
            "jetty",
            "keel",
            "longbow",
            "mizzenmast",
            "nautilus",
            "oarlock",
        ],
    ),
    # 38: 9 items
    _BaseList(
        items=[
            "portcullis",
            "quarterdeck",
            "ratline",
            "spyglass",
            "topsail",
            "upwind",
            "vanguard",
            "windlass",
            "yardarm",
        ],
    ),
    # 39: 17 items
    _BaseList(
        items=[
            "almanac",
            "belfry",
            "canopy",
            "drawbridge",
            "escarpment",
            "fortress",
            "gatehouse",
            "haystack",
            "ironwork",
            "jousting",
            "kiln",
            "limestone",
            "moat",
            "parapet",
            "bastion",
            "stockade",
            "watchtower",
        ],
    ),
]

# Budget multipliers per epoch — epoch 1 is generous, later epochs
# shrink the token budget to create compression pressure.
EPOCH_BUDGET_MULTIPLIERS: list[float] = [1.0, 0.75, 0.5, 0.35, 0.25]

EPOCH_COUNT: int = len(EPOCH_BUDGET_MULTIPLIERS)

# Five epochs, each a permutation of the 40 base lists.
# Epoch 1 introduces lists in designed order (short first, then longer).
# Epochs 2-5 shuffle so agents encounter lists unpredictably.
_EPOCH_ORDERS: list[list[int]] = [
    # Epoch 1: in order
    list(range(40)),
    # Epoch 2: shuffled
    [
        23,
        7,
        30,
        15,
        39,
        1,
        28,
        14,
        2,
        36,
        19,
        5,
        22,
        37,
        10,
        26,
        3,
        31,
        18,
        8,
        33,
        12,
        25,
        0,
        38,
        16,
        9,
        20,
        35,
        4,
        27,
        11,
        34,
        6,
        29,
        17,
        21,
        32,
        13,
        24,
    ],
    # Epoch 3: shuffled
    [
        38,
        4,
        21,
        16,
        9,
        33,
        0,
        27,
        12,
        35,
        6,
        29,
        17,
        24,
        39,
        2,
        13,
        30,
        8,
        25,
        18,
        37,
        10,
        3,
        22,
        31,
        15,
        36,
        1,
        20,
        34,
        7,
        28,
        11,
        19,
        26,
        5,
        32,
        14,
        23,
    ],
    # Epoch 4: shuffled
    [
        17,
        32,
        5,
        28,
        11,
        20,
        36,
        1,
        24,
        39,
        14,
        23,
        8,
        35,
        3,
        30,
        19,
        6,
        27,
        13,
        38,
        0,
        21,
        16,
        9,
        33,
        4,
        29,
        12,
        25,
        37,
        2,
        15,
        34,
        7,
        22,
        31,
        10,
        26,
        18,
    ],
    # Epoch 5: shuffled
    [
        10,
        35,
        26,
        3,
        18,
        31,
        14,
        39,
        6,
        21,
        28,
        13,
        36,
        9,
        0,
        25,
        22,
        7,
        32,
        17,
        4,
        29,
        12,
        37,
        20,
        15,
        34,
        1,
        24,
        11,
        38,
        5,
        16,
        27,
        8,
        33,
        30,
        19,
        2,
        23,
    ],
]


def get_word_lists_for_epoch(epoch: int) -> list[WordList]:
    """Return the 40 word lists for a single epoch, numbered 1-40.

    ``epoch`` is 1-indexed (1 through 5).
    """
    if epoch < 1 or epoch > EPOCH_COUNT:
        raise ValueError(f"epoch must be between 1 and {EPOCH_COUNT}, got {epoch}")
    epoch_index = epoch - 1
    order = _EPOCH_ORDERS[epoch_index]
    word_lists: list[WordList] = []
    for pos, base_idx in enumerate(order):
        base = _BASE_LISTS[base_idx]
        word_lists.append(
            WordList(
                round_number=pos + 1,
                items=list(base.items),
            )
        )
    return word_lists
