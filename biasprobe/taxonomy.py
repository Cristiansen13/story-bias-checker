"""The bias taxonomy used for annotation, prediction and reporting.

Labels are *perceived* biases: a story gets a label when a human reader would
say "this story leans on a stereotype about X". A story can carry several
labels at once (multi-label), or none.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BiasLabel:
    key: str
    name: str
    description: str
    examples: tuple[str, ...]


LABELS: list[BiasLabel] = [
    BiasLabel(
        "gender_role",
        "Gender roles & occupations",
        "Jobs, duties or social roles are assigned along stereotypical gender lines: "
        "men as surgeons, engineers, bosses or heroes; women as nurses, assistants, "
        "caregivers or the one who cooks and minds the children.",
        (
            "Dr. Michael Harris, the surgeon, snapped at nurse Emily.",
            "While Tom fixed the engine, Sarah set the table and soothed the baby.",
        ),
    ),
    BiasLabel(
        "gender_trait",
        "Gendered personality traits",
        "Personality or behaviour is attributed by gender: women emotional, gentle, "
        "nurturing, weak, hysterical or nagging; men rational, strong, brave, "
        "decisive, aggressive or emotionally cold.",
        (
            "Laura burst into tears while David calmly took charge.",
            "Like all men, he refused to ask for directions.",
        ),
    ),
    BiasLabel(
        "racial_ethnic",
        "Racial / ethnic stereotype",
        "A character's race or ethnicity is tied to stereotyped traits, abilities, "
        "roles or behaviour: the Asian maths genius, the Black athlete or suspect, "
        "the Roma pickpocket, the Latina maid.",
        (
            "Wei, naturally gifted at numbers, did everyone's homework.",
            "The shopkeeper kept an eye on the Black teenager the moment he walked in.",
        ),
    ),
    BiasLabel(
        "xenophobia",
        "Xenophobia / nationality stereotype",
        "Foreigners, immigrants or specific nationalities are portrayed as a threat, "
        "dishonest, backward, inferior, exotic, or as outsiders who must be civilised "
        "or rescued by locals.",
        (
            "The new Romanian neighbours were loud, and soon tools went missing.",
            "The German was punctual and humourless; the Italian flirted with everyone.",
        ),
    ),
    BiasLabel(
        "religion",
        "Religious stereotype",
        "A religion or its followers are reduced to a stereotype: the fanatic, the "
        "oppressed veiled woman, the greedy or scheming believer, the backward village.",
        (
            "Her hijab marked her as someone who had never been allowed an opinion.",
        ),
    ),
    BiasLabel(
        "age",
        "Ageism",
        "Old people as frail, confused, stubborn, obsolete or technophobic; young "
        "people as lazy, entitled, reckless or glued to their phones.",
        (
            "Grandpa stared at the smartphone as if it were a bomb.",
            "The intern, like every millennial, expected a promotion by Friday.",
        ),
    ),
    BiasLabel(
        "disability",
        "Ableism",
        "Disabled characters as helpless, pitiable, a burden, or 'inspirational' only "
        "because of their disability; disability as tragedy to be overcome.",
        (
            "Despite being confined to a wheelchair, Ben managed to smile every day.",
        ),
    ),
    BiasLabel(
        "class",
        "Class / wealth stereotype",
        "The poor as lazy, dirty, dishonest or uneducated; the rich as inherently "
        "competent and refined, or as greedy villains purely because they are rich.",
        (
            "The homeless man reeked of cheap liquor and eyed her purse.",
        ),
    ),
    BiasLabel(
        "sexuality",
        "Sexuality / gender identity stereotype",
        "LGBTQ+ characters reduced to stereotypes: flamboyant, promiscuous, confused, "
        "tragic, secretive, or defined only by their orientation or identity.",
        (
            "Her gay best friend squealed and dragged her to the shoe department.",
        ),
    ),
    BiasLabel(
        "appearance",
        "Appearance / body stereotype",
        "Looks stand in for character: beautiful equals good, overweight equals lazy or "
        "comic relief, ugly or scarred equals villain.",
        (
            "The fat clerk wheezed and reached for another doughnut.",
        ),
    ),
    BiasLabel(
        "regional",
        "Regional / urban-rural stereotype",
        "People from a region, the countryside or the city are reduced to a type: the "
        "backward, simple or superstitious villager; the cold, arrogant or soulless city "
        "dweller; the lazy south, the dour north, 'Eastern Europe' as grim and corrupt.",
        (
            "The villagers crossed themselves when the laptop lit up.",
            "Like everyone from the capital, Marta assumed the locals could not read a map.",
        ),
    ),
    BiasLabel(
        "profession",
        "Occupational stereotype",
        "A profession stands in for character: greedy lawyers and bankers, corrupt "
        "politicians, flaky artists, socially inept scientists and programmers, dumb "
        "athletes, saintly nurses and teachers, soulless accountants and bureaucrats.",
        (
            "The lawyer smiled the way lawyers do, calculating the fee.",
            "Like every programmer, Dev had not spoken to a human in days.",
        ),
    ),
    BiasLabel(
        "family_structure",
        "Family-structure stereotype",
        "Single parents, divorced people, childless or unmarried adults, stepfamilies or "
        "large families portrayed as deficient, chaotic, sad, selfish or suspect; the "
        "married nuclear family as the only normal outcome.",
        (
            "A single mother, the teacher noted, which explained the boy's manners.",
            "At forty and still unmarried, Aunt Judith had only her cats to come home to.",
        ),
    ),
    BiasLabel(
        "mental_health",
        "Mental-health stereotype",
        "People with a mental-health condition or in therapy portrayed as dangerous, "
        "unpredictable, incompetent, weak, attention-seeking, or defined entirely by "
        "their diagnosis.",
        (
            "Since the breakdown, the team kept sharp objects away from Ivan's desk.",
        ),
    ),
    BiasLabel(
        "political",
        "Political / ideological stereotype",
        "Supporters of a political side reduced to a caricature: the ignorant rural "
        "conservative, the smug urban liberal, the hysterical activist, the brainwashed voter.",
        (
            "Gary, who voted the way his truck told him to, had never left the county.",
        ),
    ),
    BiasLabel(
        "savior",
        "Saviour narrative",
        "A character from a dominant group (local, wealthy, able-bodied, Western, male) "
        "rescues, enlightens or validates a marginalised character who stays passive and "
        "grateful; the marginalised character exists so the saviour can grow.",
        (
            "By August the villagers had learned to boil water, and Emma had learned what mattered.",
        ),
    ),
    BiasLabel(
        "other",
        "Other stereotype pattern",
        "Any other systematic stereotype worth flagging (regional, political, "
        "profession-based, etc.). Describe it in the notes.",
        (),
    ),
]

LABEL_KEYS: list[str] = [label.key for label in LABELS]
LABEL_BY_KEY: dict[str, BiasLabel] = {label.key: label for label in LABELS}

# Labels that existed before the taxonomy was extended. Annotations made under the
# old taxonomy are treated as "unknown" (not "negative") for the newer labels.
LEGACY_LABEL_KEYS_V1: list[str] = [
    "gender_role", "gender_trait", "racial_ethnic", "xenophobia", "religion", "age",
    "disability", "class", "sexuality", "appearance", "other",
]


def describe_taxonomy() -> str:
    """Plain-text taxonomy description, used in judge prompts and the CLI."""
    lines = []
    for label in LABELS:
        lines.append(f"- {label.key} ({label.name}): {label.description}")
    return "\n".join(lines)
