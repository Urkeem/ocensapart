"""Authored dialogue for the complete Last Cure campaign."""


def _line(speaker, text):
    return {"speaker": speaker, "text": text}


def _node(node_id, speaker, text, *, conditions=(), actions=(), priority=0, once=False, choices=()):
    return {
        "id": node_id,
        "lines": (_line(speaker, text),),
        "conditions": tuple(conditions),
        "actions": tuple(actions),
        "priority": priority,
        "once": once,
        "choices": tuple(choices),
    }


def _status(quest_id, status):
    return {"type": "quest_status", "quest_id": quest_id, "status": status}


def _quest_dialogue(quest_id, stem, speaker, offer, reminder, turn_in, *, priority=80):
    return (
        _node(
            f"{stem}.offer", speaker, offer,
            conditions=(_status(quest_id, "available"),),
            actions=({"type": "start_quest", "quest_id": quest_id},),
            priority=priority, once=True,
        ),
        _node(
            f"{stem}.reminder", speaker, reminder,
            conditions=(_status(quest_id, "active"),), priority=priority - 10,
        ),
        _node(
            f"{stem}.turn_in", speaker, turn_in,
            conditions=(_status(quest_id, "ready_to_turn_in"),),
            actions=({"type": "turn_in_quest", "quest_id": quest_id},),
            priority=priority + 20, once=True,
        ),
    )


MORNING_CHOICES = (
    {"id": "ready", "text": "I will get started.", "response": "Thank you. The farm needs us both.", "converges_to": "accept_chores"},
    {"id": "where", "text": "Which crops need care?", "response": "The corn and tomatoes beside the farmhouse.", "converges_to": "accept_chores"},
)


WIFE_DIALOGUE = (
    _node(
        "wife.morning_chores.offer", "Wife", "Water three young plants and bring in two ripe crops for breakfast.",
        conditions=(_status("prologue.morning_chores", "available"),),
        actions=({"type": "start_quest", "quest_id": "prologue.morning_chores"},),
        priority=80, once=True, choices=MORNING_CHOICES,
    ),
    _node("wife.morning_chores.reminder", "Wife", "The corn and tomatoes still need your hands.", conditions=(_status("prologue.morning_chores", "active"),), priority=70),
    _node(
        "wife.morning_chores.turn_in", "Wife", "Breakfast is saved. You always make this place feel possible.",
        conditions=(_status("prologue.morning_chores", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "prologue.morning_chores"},), priority=100, once=True,
    ),
    _node("wife.morning_chores.complete", "Wife", "The crops look brighter already.", conditions=(_status("prologue.morning_chores", "completed"),), priority=90, once=True),
    *_quest_dialogue("prologue.first_defense", "wife.first_defense", "Wife", "Raiders are coming up the farm road. Take your weapon!", "They are at the edge of the fields.", "The farm still stands. Ironveil will hear what you did.", priority=85),
    *_quest_dialogue("prologue.wifes_illness", "wife.illness", "Wife", "Something is wrong. The blight burns in my lungs. Find Lillian in the village.", "Please find Lillian. She knows every healer in Ironveil.", "Lillian believes the missing Alchemist can help us.", priority=86),
    *_quest_dialogue("act6.final_farm_defense", "wife.final_defense", "Wife", "The Necromancer has sent everything left against our home. We hold together.", "The final host is gathering beyond the crops.", "We survived because every person you saved stood with us.", priority=88),
    _node(
        "wife.last_cure.turn_in", "Wife", "The fever is gone. For the first time in years, I can breathe without pain.",
        conditions=(_status("act8.craft_last_cure", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "act8.craft_last_cure"},), priority=110, once=True,
    ),
    *_quest_dialogue("act8.grow_cured_crops", "wife.cured_crops", "Wife", "Let us prove the cure can heal the soil. Grow three healthy corn or tomato crops.", "The new growth will tell us whether the land is healing.", "Green leaves across blighted soil. Take these seed bags to our allies.", priority=88),
    _node(
        "wife.distribution.turn_in", "Wife", "Every field has a beginning again. Come—look at what Ironveil has become.",
        conditions=(_status("act8.distribute_cure", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "act8.distribute_cure"},), priority=110, once=True,
    ),
    *_quest_dialogue("epilogue.rebuilding", "wife.epilogue", "Wife", "Walk with me through the farm we rebuilt together.", "Everyone is waiting by the new fields.", "This is our home again—and now it is theirs too.", priority=92),
    _node(
        "wife.epilogue.community", "Wife", "Hunter's survivors have homes, the royal family is whole, and the Alchemist's family tends the medicine garden.",
        conditions=(
            {"type": "flag", "flag": "game.story_complete"},
            {"type": "flag", "flag": "farm.hunter_survivors_settled"},
            {"type": "flag", "flag": "act5.princess_rescued"},
        ), priority=130,
    ),
    _node("wife.ambient", "Wife", "We will see this through together.", priority=-100),
)


LILLIAN_DIALOGUE = (
    _node(
        "lillian.illness_lead", "Lillian", "The illness carries the blight's mark. Our Alchemist was taken near the village road.",
        conditions=(_status("prologue.wifes_illness", "active"),), priority=100, once=True,
    ),
    _node(
        "lillian.illness.turn_in", "Lillian", "Free the Alchemist. No one else can slow this sickness.",
        conditions=(_status("prologue.wifes_illness", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "prologue.wifes_illness"},), priority=110, once=True,
    ),
    *_quest_dialogue("act1.rescue_alchemist", "lillian.alchemist_rescue", "Lillian", "The captors are close. Clear them out and bring the Alchemist home.", "The raiders hold the east side of the village.", "You found our healer. Ironveil owes you more than it knows."),
    *_quest_dialogue("pirate.open_market_stall", "lillian.market_stall", "Lillian", "Build a wheelbarrow for the empty coastal stall. I know a sailor who will notice it.", "The stall needs a wheelbarrow before it can open.", "There—Pirate never passes a new market without stopping.", priority=75),
    _node("lillian.ambient", "Lillian", "The village talks about the farm that would not fall.", priority=-100),
)


ALCHEMIST_DIALOGUE = (
    _node(
        "alchemist.rescue.turn_in", "Alchemist", "You broke their circle. I can work again—and I may be able to help your Wife.",
        conditions=(_status("act1.rescue_alchemist", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "act1.rescue_alchemist"},), priority=110, once=True,
    ),
    *_quest_dialogue("act1.temporary_medicine", "alchemist.temporary_medicine", "Alchemist", "Corn, tomato, and a bitter weed will buy her time. Craft the mixture at once.", "Bring me the temporary medicine when it is mixed.", "This will steady her, but it cannot cure the blight."),
    *_quest_dialogue("act6.rescue_alchemist_family", "alchemist.family", "Alchemist", "The enemy moved my family near the village. Free them; they guard the Potion of Life.", "My family and the first potion are still in enemy hands.", "They are safe. The Potion of Life is yours."),
    *_quest_dialogue("act8.craft_last_cure", "alchemist.last_cure", "Alchemist", "Life, Memory, and Vigor must become one draught. Craft the Last Cure.", "Combine all three potions in my workspace.", "Take it to your Wife before the blight changes again."),
    *_quest_dialogue("act8.distribute_cure", "alchemist.distribution", "Alchemist", "Five allies can spread these cured seeds across the kingdom.", "Give one bag each to me, Hunter, Pirate, the Princess, and the King.", "The treatment is recorded. It will never be lost again.", priority=75),
    _node(
        "alchemist.cure.delivery", "Alchemist", "My medicine garden will supply every village clinic.",
        conditions=(_status("act8.distribute_cure", "active"), {"type": "has_item", "item_id": "cured_seed_bag"}),
        actions=({"type": "take_item", "item_id": "cured_seed_bag"}, {"type": "reveal_favorite", "npc_id": "alchemist", "plant_id": "lavender"}), priority=100, once=True,
    ),
    _node("alchemist.ambient", "Alchemist", "A cure begins with careful work and one stubborn hope.", priority=-100),
)


HUNTER_DIALOGUE = (
    *_quest_dialogue("act2.recruit_hunter", "hunter.recruit", "Hunter", "I join people who can read a trail. Show me you notice what others miss.", "Follow the broken branches, then tell me where they lead.", "Correct. I will guide you through the Holds."),
    _node("hunter.recruit.trial", "Hunter", "The tracks turn north beneath a snapped ash branch. You saw it too.", conditions=(_status("act2.recruit_hunter", "active"),), priority=100, once=True),
    *_quest_dialogue("holds.ashfall", "hunter.ashfall", "Hunter", "The map marks Ashfall first. Clear it before its patrols regroup.", "Ashfall lies through the village's northern route.", "The first mark on the map is gone."),
    *_quest_dialogue("holds.blackthorn", "hunter.blackthorn", "Hunter", "Blackthorn is deeper and better guarded. Stay mobile.", "Blackthorn waits below Ashfall.", "Two Holds broken. Grimroot is next."),
    *_quest_dialogue("holds.grimroot", "hunter.grimroot", "Hunter", "Grimroot holds captives. We clear it, then Pirate extracts everyone.", "Find me inside Grimroot after its jailers fall.", "The survivors are settling at the farm. You gave them a future."),
    _node(
        "hunter.grimroot.extraction", "Hunter", "The captives are free. Pirate has the extraction route—move them now.",
        conditions=(_status("holds.grimroot", "active"), {"type": "flag", "flag": "holds.hold_3_encounter_complete"}),
        actions=({"type": "survivor_sequence"},), priority=105, once=True,
    ),
    *_quest_dialogue("holds.hollow_crypt", "hunter.hollow_crypt", "Hunter", "The crypt key opens Hold IV. The royal tiara should be inside.", "Use the key at the Hollow Crypt.", "The tiara proves the royal prisoners survived."),
    _node(
        "hunter.cure.delivery", "Hunter", "The rescued families will plant this beyond the new homes.",
        conditions=(_status("act8.distribute_cure", "active"), {"type": "has_item", "item_id": "cured_seed_bag"}),
        actions=({"type": "take_item", "item_id": "cured_seed_bag"}, {"type": "reveal_favorite", "npc_id": "hunter", "plant_id": "tomato"}), priority=100, once=True,
    ),
    _node("hunter.ambient", "Hunter", "A safe trail is one somebody fought to make.", priority=-100),
)


NAVIGATOR_DIALOGUE = (
    *_quest_dialogue("act2.recover_kingdom_map", "navigator.map", "Navigator", "You want the Holds? Then ask the question you came to ask.", "Choose your words. The kingdom map has cost lives.", "Take the map. May you use it better than I did."),
    _node(
        "navigator.map.confront", "Navigator", "I hid the map so the Necromancer could not find the captives. What do you believe?",
        conditions=(_status("act2.recover_kingdom_map", "active"),), priority=100, once=True,
        choices=(
            {"id": "believe", "text": "I believe you.", "response": "Then finish what I could not.", "actions": ({"type": "set_dialogue_fact", "fact": "navigator.approach", "value": "mercy"},)},
            {"id": "challenge", "text": "You should have warned us.", "response": "You are right. Take the truth and the map.", "actions": ({"type": "set_dialogue_fact", "fact": "navigator.approach", "value": "challenge"},)},
        ),
    ),
    _node("navigator.ambient", "Navigator", "Every safe road was once an unknown line.", priority=-100),
)


KING_DIALOGUE = (
    *_quest_dialogue("act3.save_queen", "king.queen", "King", "The Queen has the same blight. Bring her the Alchemist's royal medicine.", "The Queen waits in the castle hall.", "You returned hope to this house and kingdom."),
    *_quest_dialogue("act3.royal_aid", "king.royal_aid", "King", "Two soldiers will join your farm. Our scouts also found proof that the Princess lives.", "Accept the soldiers and carry the news.", "The crown now fights beside the farm."),
    *_quest_dialogue("holds.ironveil_prison", "king.prison", "King", "The tiara confirms it. Use the Ironveil Key and bring my daughter home.", "The Princess is held in the Fifth Hold.", "My family is whole because you refused to abandon her."),
    _node(
        "king.cure.delivery", "King", "These seeds will restore the crown farms and feed Ironveil.",
        conditions=(_status("act8.distribute_cure", "active"), {"type": "has_item", "item_id": "cured_seed_bag"}),
        actions=({"type": "take_item", "item_id": "cured_seed_bag"}, {"type": "reveal_favorite", "npc_id": "king", "plant_id": "corn"}), priority=100, once=True,
    ),
    _node("king.ambient", "King", "The throne remembers who stood when the walls failed.", priority=-100),
)


QUEEN_DIALOGUE = (
    _node(
        "queen.medicine.turn_in", "Queen", "The medicine is working. Tell the Alchemist their skill has saved a kingdom.",
        conditions=(_status("act3.save_queen", "ready_to_turn_in"), {"type": "has_item", "item_id": "royal_medicine"}),
        actions=({"type": "turn_in_quest", "quest_id": "act3.save_queen"},), priority=110, once=True,
    ),
    _node("queen.ambient", "Queen", "The castle doors are open to the farm's friends.", priority=-100),
)


PIRATE_DIALOGUE = (
    _node(
        "pirate.market_stall.turn_in", "Pirate", "A fresh stall on a dying coast? That is either courage or excellent bait. I approve.",
        conditions=(_status("pirate.open_market_stall", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "pirate.open_market_stall"},), priority=105, once=True,
    ),
    *_quest_dialogue("pirate.befriend", "pirate.befriend", "Pirate", "Lillian saved a bottle for people planning impossible voyages. Share it and tell me yours.", "The rum is open. Speak plainly.", "You have my boat, my ship, and my word."),
    _node("pirate.befriend.rum", "Pirate", "To lost shores, found friends, and maps too dangerous to ignore.", conditions=(_status("pirate.befriend", "active"),), priority=100, once=True),
    *_quest_dialogue("act7.necromancer_citadel", "pirate.citadel", "Pirate", "The Citadel lies beyond ordinary waters. My ship can make the crossing.", "Board when you are ready. We sail for the Citadel.", "The Necromancer is finished. Take the last potions home."),
    _node(
        "pirate.cure.delivery", "Pirate", "I will carry these seeds to every island port that will have me.",
        conditions=(_status("act8.distribute_cure", "active"), {"type": "has_item", "item_id": "cured_seed_bag"}),
        actions=({"type": "take_item", "item_id": "cured_seed_bag"}, {"type": "reveal_favorite", "npc_id": "pirate", "plant_id": "chili_pepper"}), priority=100, once=True,
    ),
    _node("pirate.ambient", "Pirate", "A good voyage changes the harbor you return to.", priority=-100),
)


PRINCESS_DIALOGUE = (
    _node(
        "princess.prison.turn_in", "Princess", "You carried my mother's tiara into this darkness. Lead me home.",
        conditions=(_status("holds.ironveil_prison", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "holds.ironveil_prison"},), priority=110, once=True,
    ),
    _node(
        "princess.cure.delivery", "Princess", "The prison settlements will receive these first.",
        conditions=(_status("act8.distribute_cure", "active"), {"type": "has_item", "item_id": "cured_seed_bag"}),
        actions=({"type": "take_item", "item_id": "cured_seed_bag"}, {"type": "reveal_favorite", "npc_id": "princess", "plant_id": "sunflower"}), priority=100, once=True,
    ),
    _node("princess.ambient", "Princess", "We will rebuild beyond the castle walls.", priority=-100),
)


NECROMANCER_DIALOGUE = (
    _node(
        "necromancer.citadel.turn_in", "Necromancer", "Take your little bottles. The blight has already taught your kingdom fear.",
        conditions=(_status("act7.necromancer_citadel", "ready_to_turn_in"),),
        actions=({"type": "turn_in_quest", "quest_id": "act7.necromancer_citadel"},), priority=110, once=True,
        choices=(
            {"id": "reject", "text": "Ironveil learned hope.", "response": "Then carry it home while you can."},
            {"id": "silence", "text": "Say nothing.", "response": "Your silence changes nothing."},
        ),
    ),
    _node("necromancer.ambient", "Necromancer", "All harvests end.", priority=-100),
)


JIM_DIALOGUE = (
    _node(
        "jim.upgrades.introduction", "Jim", "Bring me good materials and I can improve your tools and weapons.",
        conditions=({"type": "flag", "flag": "services.jim_upgrades", "value": False},),
        actions=({"type": "set_flag", "flag": "services.jim_upgrades"}, {"type": "open_upgrade_service"}), priority=20, once=True,
    ),
    _node("jim.upgrades.service", "Jim", "Let us see what needs strengthening.", conditions=({"type": "flag", "flag": "services.jim_upgrades"},), actions=({"type": "open_upgrade_service"},), priority=10),
    _node("jim.ambient", "Jim", "Keep your tools dry and your edge clean.", priority=-100),
)


VILLAGER_DIALOGUE = (
    _node("villager.restored", "Villager", "Healthy crops are growing beyond the village again.", conditions=({"type": "flag", "flag": "world.kingdom_restored"},), priority=10),
    _node("villager.ambient", "Villager", "Keep an eye on the roads beyond Ironveil.", priority=-100),
)


MERCHANT_CAMPAIGN_DIALOGUE = (
    _node("merchant.shop.greeting", "Merchant", "Welcome. Have a look at today's stock.", actions=({"type": "open_shop"},)),
)


CAMPAIGN_DIALOGUE_DEFINITIONS = {
    "wife": WIFE_DIALOGUE,
    "lillian": LILLIAN_DIALOGUE,
    "alchemist": ALCHEMIST_DIALOGUE,
    "hunter": HUNTER_DIALOGUE,
    "navigator": NAVIGATOR_DIALOGUE,
    "king": KING_DIALOGUE,
    "queen": QUEEN_DIALOGUE,
    "pirate": PIRATE_DIALOGUE,
    "princess": PRINCESS_DIALOGUE,
    "necromancer": NECROMANCER_DIALOGUE,
    "jim": JIM_DIALOGUE,
    "villager": VILLAGER_DIALOGUE,
    "merchant": MERCHANT_CAMPAIGN_DIALOGUE,
}

DIALOGUE_DEFINITIONS = CAMPAIGN_DIALOGUE_DEFINITIONS
