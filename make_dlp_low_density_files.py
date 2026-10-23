"""Generate .txt files of ordinary, harmless text with at most 5 sensitive values each.

Companion to make_dlp_test_files.py (same sizes: 50 files, 2 KB .. 100 MB). The
body of each file is realistic non-sensitive writing — a hiking guide, a
gardening handbook, a recipe collection, astronomy notes and so on — with no
names, organisations, money, health terms or long digit runs. Into that text,
1 to 5 sensitive values are planted (an email, a card number, an Aadhaar, a
diagnosis ...), one value per sentence, at random positions. manifest.csv lists
every planted value per file: the answer key for checking what the DLP finds.

No sentence is repeated within a file (same rule and checker as the main set).

    python make_dlp_low_density_files.py                    # low: 1-5 values per file -> ./dlp_samples_low
    python make_dlp_low_density_files.py --density medium   # medium: ~1 value per KB  -> ./dlp_samples_medium
    python make_dlp_low_density_files.py --max-items 3 --out other_dir

Needs make_dlp_test_files.py next to it (it reuses its ID builders).
"""
import argparse
import csv
import os
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta

import make_dlp_test_files as base
from make_dlp_test_files import (DISEASES, DRUGS, IN_CITIES, Gen, fmt_d, human, merge_answer_parts, sentence_keys,
                                 split_answer_key, type_counts, write_answer_part)

# Words the harmless text must never contain: the DLP's own keyword lists
# (malware, adult, vulgar), business-sensitive (BESD) vocabulary, and health,
# finance and personal terms. Any filler sentence containing one is redrawn.
_BANNED_WORDS = {
    "worm", "worms", "virus", "infection", "infected", "exploit", "payload", "zombie", "rat", "rats", "trojan", "backdoor",
    "sniffer", "dropper", "downloader", "polymorphic", "hijacker", "malware", "spyware", "adult", "adults", "bloody",
    "damn", "crap", "jerk", "cock", "hardcore", "uncensored", "porn", "explicit", "monitor", "monitoring", "tracking",
    "security", "alert", "password", "login", "account", "accounts", "customer", "customers", "client", "invoice", "payment",
    "contract", "agreement", "revenue", "budget", "profit", "cash", "price", "pricing", "discount", "sales", "market",
    "supplier", "vendor", "inventory", "stock", "warehouse", "shipping", "freight", "delivery", "order", "orders",
    "purchase", "procurement", "incident", "breach", "vulnerability", "patent", "trademark", "research", "prototype",
    "compliance", "audit", "policy", "network", "server", "database", "code", "api", "function", "class", "repository",
    "deployment", "strategy", "roadmap", "board", "merger", "legal", "court", "employee", "salary", "ticket", "subscription",
    "feedback", "complaint", "patient", "doctor", "hospital", "health", "medical", "disease", "diagnosis", "medication",
    "bank", "card", "loan", "tax", "insurance", "secret", "confidential", "private", "identity", "address", "phone", "email",
}
BANNED = re.compile(r"\b(?:" + "|".join(sorted(_BANNED_WORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)

MONTHS = "January February March April May June July August September October November December".split()
ORD = ["first", "second", "third", "fourth", "last"]
COLOURS = ["red", "blue", "yellow", "white", "orange", "green"]


def _r(g, a, b):
    return g.r.randint(a, b)


def _f(g, a, b, nd=1):
    return round(g.r.uniform(a, b), nd)


# ----------------------------------------------------------------------------
# Harmless topics. Each template draws several words and numbers, so a sentence
# repeats only by coincidence (and the per-file checker redraws it then).
# ----------------------------------------------------------------------------
def hiking(g):
    P = ["ridge", "saddle", "meadow", "river ford", "switchback", "cairn", "viewpoint", "spring", "boulder field", "pine grove",
         "scree slope", "footbridge", "waterfall", "rock shelf", "larch stand", "hut", "lake shore", "col", "gully", "summit"]
    F = ["wildflowers", "ferns", "mosses", "lichens", "blueberries", "alpine roses", "orchids", "heather", "gentians", "saxifrages"]
    p1, p2 = g.r.sample(P, 2)
    return g.pick([
        f"From the {p1} to the {p2} the path climbs about {_r(g, 40, 900)} metres over {_f(g, 0.4, 9)} kilometres, so most walkers need {_r(g, 15, 240)} minutes for this stretch.",
        f"In {g.pick(MONTHS)} the {p1} is usually {g.pick(['dry', 'muddy', 'icy', 'waterlogged', 'dusty', 'firm'])}, and the {g.pick(F)} along its edge peak around the {g.pick(ORD)} week.",
        f"Carry at least {_f(g, 0.5, 4)} litres of water, because the spring below the {p1} dries up after {_r(g, 2, 9)} weeks without rain.",
        f"A {g.pick(COLOURS)} marker on every {_r(g, 3, 25)}th post shows the turn towards the {p2}, about {_f(g, 0.2, 6)} kilometres past the {p1}.",
        f"The descent from the {p1} drops {_r(g, 80, 1200)} metres in {_f(g, 1, 8)} kilometres, which feels hard on the knees after a {_r(g, 3, 10)}-hour day.",
        f"Mobile signal fades {_f(g, 0.3, 7)} kilometres beyond the {p1} and comes back only near the {p2}.",
        f"Snow can linger on the {p1} until {g.pick(MONTHS)}, and light traction spikes help on the steepest {_r(g, 20, 400)} metres.",
        f"The camping area near the {p1} has room for {_r(g, 3, 40)} tents on flat ground about {_r(g, 10, 300)} metres from the stream.",
        f"After {_r(g, 2, 30)} millimetres of rain the {p1} crossing can rise by {_r(g, 5, 60)} centimetres within {_r(g, 1, 6)} hours.",
        f"Groups of more than {_r(g, 4, 20)} walkers should split before the {p1}, where the trail narrows to {_f(g, 0.4, 1.5)} metres for {_r(g, 50, 700)} metres.",
    ])


def gardening(g):
    PL = ["tomato", "basil", "chilli", "lettuce", "spinach", "marigold", "bean", "pea", "carrot", "radish", "coriander", "mint",
          "brinjal", "okra", "cucumber", "sunflower", "rose", "jasmine", "curry leaf", "hibiscus"]
    S = ["sandy loam", "clay soil", "potting mix", "compost-rich bed", "raised bed", "cocopeat blend", "red soil", "terrace pot"]
    p = g.pick(PL)
    return g.pick([
        f"{p.capitalize()} seedlings in {g.pick(S)} usually need {_r(g, 2, 25)} to {_r(g, 26, 60)} millilitres of water every {_r(g, 1, 6)} days in {g.pick(MONTHS)}.",
        f"Sow {p} seeds about {_f(g, 0.3, 3)} centimetres deep and {_r(g, 5, 60)} centimetres apart, then expect sprouts in {_r(g, 3, 21)} days.",
        f"A {_r(g, 2, 12)}-centimetre layer of mulch kept the {g.pick(S)} around the {p} plants {_r(g, 2, 9)} degrees cooler at noon.",
        f"Pinching the top {_r(g, 2, 8)} leaves of each {p} stem after week {_r(g, 3, 9)} gave {_r(g, 2, 6)} extra side shoots per plant.",
        f"The {p} bed needs about {_r(g, 4, 9)} hours of direct sun, so the {g.pick(['east', 'west', 'south', 'north'])} corner suits it best from {g.pick(MONTHS)} onwards.",
        f"Feed the {p} plants with diluted seaweed liquid every {_r(g, 7, 30)} days, using roughly {_r(g, 5, 40)} millilitres per {_r(g, 1, 10)} litres of water.",
        f"Yellowing on the lower {p} leaves after {_r(g, 2, 10)} cloudy days usually means the {g.pick(S)} is staying too wet.",
        f"A trellis {_f(g, 0.8, 2.5)} metres tall supported {_r(g, 3, 14)} {p} vines along a {_r(g, 2, 12)}-metre fence.",
        f"Harvest the {p} {g.pick(['in the early morning', 'before the midday heat', 'after the dew dries', 'late in the evening'])}, roughly {_r(g, 40, 120)} days after sowing.",
        f"Rotating the {p} patch with {g.pick(PL)} every {_r(g, 1, 3)} seasons kept the {g.pick(S)} loose and easy to dig.",
    ])


def cooking(g):
    D = ["lentil soup", "vegetable pulao", "banana bread", "tomato rasam", "masala dosa batter", "mint chutney", "oat cookies",
         "paneer tikka", "lemon rice", "sourdough loaf", "coconut stew", "pumpkin curry", "rava upma", "chickpea salad"]
    I = ["onions", "garlic", "ginger", "curry leaves", "mustard seeds", "cumin", "tomatoes", "coconut milk", "rice flour",
         "butter", "brown sugar", "yoghurt", "lentils", "spinach", "potatoes", "carrots"]
    d = g.pick(D)
    return g.pick([
        f"For the {d}, soak {_r(g, 50, 600)} grams of {g.pick(I)} for {_r(g, 10, 240)} minutes before cooking.",
        f"Heat the pan for about {_r(g, 30, 180)} seconds, then add {_r(g, 1, 4)} tablespoons of oil and {_r(g, 1, 3)} teaspoons of {g.pick(I)} for the {d}.",
        f"Bake the {d} at {_r(g, 150, 230)} degrees for {_r(g, 12, 70)} minutes, turning the tray after {_r(g, 5, 30)} minutes.",
        f"The {d} keeps for {_r(g, 1, 5)} days in a closed box in the fridge and for {_r(g, 2, 12)} weeks in the freezer.",
        f"Add {_r(g, 100, 900)} millilitres of water to the {d} and simmer for {_r(g, 5, 45)} minutes until the {g.pick(I)} soften.",
        f"A pinch of {g.pick(I)} added in the last {_r(g, 1, 10)} minutes gives the {d} a brighter finish.",
        f"This {d} serves {_r(g, 2, 12)} people and takes about {_r(g, 15, 120)} minutes from start to table.",
        f"Grind {_r(g, 1, 6)} cups of {g.pick(I)} with {_r(g, 1, 4)} cups of {g.pick(I)} to make the base for the {d}.",
        f"Let the {d} rest for {_r(g, 5, 60)} minutes after cooking so the {g.pick(I)} settle into the sauce.",
        f"Doubling the {d} works well if you cook it in {_r(g, 2, 4)} batches of {_r(g, 300, 1500)} grams each.",
    ])


def astronomy(g):
    O = ["Jupiter", "Saturn", "Mars", "Venus", "the Moon", "the Orion Nebula", "the Pleiades", "Andromeda", "Sirius", "Vega",
         "the Ring Nebula", "Betelgeuse", "the Double Cluster", "Albireo", "Arcturus", "the Beehive Cluster"]
    T = ["the 8-inch reflector", "the 70 mm refractor", "10x50 binoculars", "the small travel scope", "the 5-inch Maksutov"]
    o = g.pick(O)
    return g.pick([
        f"{o} rose {_r(g, 5, 80)} degrees above the {g.pick(['eastern', 'western', 'southern', 'northern'])} horizon by {_r(g, 7, 11)}.{_r(g, 10, 59)} in the evening.",
        f"Through {g.pick(T)} at {_r(g, 20, 300)}x, {o} showed {g.pick(['fine detail', 'a soft glow', 'two clear bands', 'sharp edges', 'faint colour'])} for about {_r(g, 2, 40)} minutes.",
        f"Seeing was about {_r(g, 1, 5)} out of 5 and transparency {_r(g, 1, 5)} out of 5 when {o} crossed the meridian.",
        f"The sky reading was {_f(g, 17.5, 21.9, 2)} magnitudes per square arcsecond, good enough to spot {o} without a filter.",
        f"Dew formed on the eyepiece after {_r(g, 15, 120)} minutes, so the heater strip was set to level {_r(g, 1, 5)} for {o}.",
        f"Cooling {g.pick(T)} for {_r(g, 10, 60)} minutes before pointing at {o} removed most of the tube currents.",
        f"A {_r(g, 2, 30)}-second exposure at ISO {g.pick([400, 800, 1600, 3200])} caught {o} with {_r(g, 3, 40)} faint stars around it.",
        f"{o} was {g.pick(['easy', 'tricky', 'impossible', 'just visible'])} to find with {g.pick(T)} at {_r(g, 9, 23)}.{_r(g, 10, 59)}, about {_r(g, 2, 15)} days after the new moon.",
        f"Wind gusts of {_r(g, 5, 45)} kilometres per hour shook {g.pick(T)} and blurred {o} every {_r(g, 5, 60)} seconds.",
        f"The session ended at {_r(g, 21, 23)}.{_r(g, 10, 59)} after {_r(g, 3, 25)} targets, with {o} the clear highlight.",
    ])


def birds(g):
    B = ["kingfisher", "drongo", "bulbul", "sunbird", "hornbill", "egret", "heron", "bee-eater", "barbet", "myna", "kite",
         "woodpecker", "robin", "warbler", "pond heron", "lapwing", "cormorant", "oriole", "tailorbird", "shikra"]
    H = ["reed bed", "mudflat", "banyan tree", "paddy edge", "lake bund", "scrub patch", "canal edge", "teak grove", "garden hedge"]
    b = g.pick(B)
    return g.pick([
        f"At point {_r(g, 1, 60)}, {_r(g, 1, 40)} {b}s were counted around the {g.pick(H)} in {_r(g, 5, 20)} minutes.",
        f"The {b} pair near the {g.pick(H)} returned to the same perch {_r(g, 2, 15)} times between {_r(g, 6, 9)} and {_r(g, 10, 11)} in the morning.",
        f"Water levels along the {g.pick(H)} fell by {_r(g, 5, 80)} centimetres, and {b} numbers there dropped from {_r(g, 10, 60)} to {_r(g, 1, 9)}.",
        f"A juvenile {b} was seen feeding on the {g.pick(H)} for {_r(g, 2, 25)} minutes at a distance of about {_r(g, 10, 200)} metres.",
        f"Wind of {_r(g, 2, 30)} kilometres per hour kept the {b}s low over the {g.pick(H)} during transect {_r(g, 1, 20)}.",
        f"The {b} call carried roughly {_r(g, 50, 600)} metres across the {g.pick(H)} on the {g.pick(ORD)} survey morning in {g.pick(MONTHS)}.",
        f"Over {_r(g, 2, 12)} visits, the {g.pick(H)} held {_r(g, 4, 40)} species, with the {b} recorded on {_r(g, 1, 12)} of them.",
        f"Cloud cover of {_r(g, 1, 8)} oktas reduced {b} activity along the {g.pick(H)} after {_r(g, 9, 12)} o'clock.",
        f"Nest {_r(g, 1, 90)}, built by a {b} about {_f(g, 1, 12)} metres up, held {_r(g, 1, 5)} eggs on day {_r(g, 2, 30)} of the season.",
        f"The {b} flock left the {g.pick(H)} heading {g.pick(['north', 'south', 'east', 'west'])} at roughly {_r(g, 15, 60)} kilometres per hour.",
    ])


def home_repair(g):
    J = ["leaking tap", "squeaky door hinge", "loose tile", "blocked drain", "peeling paint", "sticking window", "cracked grout",
         "wobbly shelf", "dripping cistern", "damp wall patch", "loose cabinet handle", "noisy ceiling fan"]
    T = ["adjustable spanner", "silicone sealant", "putty knife", "drill with a 6 mm bit", "sandpaper", "plumber's tape",
         "screwdriver set", "spirit level", "grout float", "wall plugs"]
    j = g.pick(J)
    return g.pick([
        f"To fix the {j}, switch off the supply and allow {_r(g, 5, 60)} minutes for the area to dry before starting.",
        f"The {j} took about {_r(g, 10, 180)} minutes with a {g.pick(T)} and needed {_r(g, 1, 4)} attempts to get right.",
        f"Apply a bead of about {_r(g, 2, 9)} millimetres along the {j} and smooth it within {_r(g, 2, 15)} minutes.",
        f"Leave the repaired {j} untouched for {_r(g, 6, 72)} hours so the filler can cure at room temperature.",
        f"For the {j}, a {g.pick(T)} and a {g.pick(T)} cover most cases, with a spare kit costing very little at a local shop.",
        f"Check the {j} again after {_r(g, 1, 8)} weeks, because small gaps of {_f(g, 0.5, 4)} millimetres can return in humid months.",
        f"Sanding the area around the {j} with grit {g.pick([80, 120, 180, 240, 320])} gave a smooth surface after {_r(g, 2, 15)} passes.",
        f"Two thin coats on the {j}, {_r(g, 2, 8)} hours apart, held better than one thick coat in the {g.pick(['kitchen', 'bathroom', 'balcony', 'utility room', 'hallway'])}.",
        f"Tightening the {j} by a quarter turn every {_r(g, 2, 12)} months stopped the problem for about {_r(g, 1, 4)} years.",
        f"Measure the {j} twice, since a {_r(g, 2, 10)}-millimetre error meant redoing the job in the {g.pick(['kitchen', 'bathroom', 'bedroom', 'hallway'])}.",
    ])


def photography(g):
    S = ["sunrise over the lake", "street bazaar", "temple courtyard", "monsoon clouds", "night skyline", "forest stream",
         "harbour boats", "flower close-up", "desert dunes", "railway platform", "festival lights", "misty valley"]
    s = g.pick(S)
    return g.pick([
        f"For the {s}, f/{g.pick(['2.8', '4', '5.6', '8', '11', '16'])} at 1/{g.pick([60, 125, 250, 500, 1000])} second and ISO {g.pick([100, 200, 400, 800, 1600])} gave a balanced exposure.",
        f"The {s} looked best about {_r(g, 5, 50)} minutes after {g.pick(['sunrise', 'sunset'])}, when the light dropped by {_r(g, 1, 4)} stops.",
        f"A {_r(g, 10, 600)} mm focal length compressed the {s} and kept {_r(g, 2, 9)} layers of the scene in view.",
        f"Bracketing {_r(g, 3, 9)} frames at {_f(g, 0.3, 2)} stop intervals saved the highlights in the {s}.",
        f"A {_r(g, 2, 30)}-second exposure on a tripod smoothed the movement in the {s}.",
        f"Shooting the {s} from {_f(g, 0.5, 30)} metres away with the camera at waist height gave a stronger foreground.",
        f"White balance around {g.pick([3200, 4500, 5200, 5600, 6500])} kelvin kept the {s} close to what the eye saw.",
        f"Of the {_r(g, 20, 600)} frames from the {s}, only {_r(g, 2, 19)} were sharp enough to print at {_r(g, 20, 90)} centimetres wide.",
        f"A polarising filter turned by about {_r(g, 10, 90)} degrees cut the glare on the {s}.",
        f"Burst mode at {_r(g, 5, 20)} frames per second caught the moment in the {s} on the {g.pick(ORD)} try.",
    ])


def coffee(g):
    M = ["pour-over", "French press", "AeroPress", "moka pot", "South Indian filter", "cold brew", "espresso", "siphon"]
    B = ["Chikmagalur", "Coorg", "Araku Valley", "Yercaud", "Wayanad", "Nilgiris", "Baba Budangiri", "Pulney Hills"]
    m = g.pick(M)
    return g.pick([
        f"The {m} used {_r(g, 12, 30)} grams of {g.pick(B)} beans to {_r(g, 180, 500)} grams of water at {_r(g, 85, 96)} degrees.",
        f"A grind setting of {_r(g, 8, 30)} on the burr grinder gave a {m} brew time of {_r(g, 1, 4)} minutes {_r(g, 0, 59)} seconds.",
        f"Beans roasted {_r(g, 5, 30)} days earlier tasted {g.pick(['brighter', 'flatter', 'sweeter', 'more bitter', 'rounder'])} in the {m} than fresh ones.",
        f"Blooming the {m} for {_r(g, 20, 60)} seconds with {_r(g, 30, 80)} grams of water released most of the trapped gas.",
        f"The {g.pick(B)} lot showed notes of {g.pick(['cocoa', 'jaggery', 'orange peel', 'spice', 'caramel', 'berries'])} at a {_f(g, 1, 3)} to {_r(g, 14, 18)} ratio in the {m}.",
        f"Stirring the {m} {_r(g, 1, 6)} times after {_r(g, 10, 50)} seconds evened out the extraction.",
        f"Cooling the {m} cup to {_r(g, 50, 70)} degrees brought out the {g.pick(['sweetness', 'acidity', 'body', 'aroma'])} of the {g.pick(B)} beans.",
        f"Descaling the {m} kettle every {_r(g, 2, 12)} weeks kept the water flow steady at about {_r(g, 4, 12)} grams per second.",
        f"Storing the {g.pick(B)} beans in an airtight jar kept them fresh for roughly {_r(g, 2, 6)} weeks after opening.",
        f"The {m} recipe scaled well from {_r(g, 1, 2)} to {_r(g, 3, 6)} cups by keeping the water at {_r(g, 15, 17)} times the coffee weight.",
    ])


TOPICS = {
    "hiking_guide":        ("Hiking trail guide", "Trail notes", hiking),
    "gardening_handbook":  ("Kitchen gardening handbook", "Growing notes", gardening),
    "recipe_collection":   ("Home recipe collection", "Recipe notes", cooking),
    "astronomy_log":       ("Amateur astronomy observing log", "Observing session", astronomy),
    "bird_survey":         ("Bird survey field notes", "Survey notes", birds),
    "home_repair_manual":  ("Home repair manual", "Repair guide", home_repair),
    "photography_tips":    ("Photography field tips", "Shooting notes", photography),
    "coffee_brewing":      ("Coffee brewing notebook", "Brewing notes", coffee),
}
TOPIC_ORDER = list(TOPICS)

# Endings appended to a sentence that keeps clashing with ones already written.
TRAILERS = [
    lambda g: f", as noted on visit {_r(g, 1, 999)} in {g.pick(MONTHS)} {_r(g, 2019, 2026)}.",
    lambda g: f", according to the log for week {_r(g, 1, 52)} of {_r(g, 2015, 2026)}.",
    lambda g: f", based on round {_r(g, 1, 999)} of the {g.pick(['spring', 'summer', 'monsoon', 'autumn', 'winter'])} notes.",
    lambda g: f", which matched entry {_r(g, 1, 9999)} in the {g.pick(ORD)} notebook.",
]


# ----------------------------------------------------------------------------
# Planted sensitive values: one value per sentence, no other personal data
# ----------------------------------------------------------------------------
def plant(g, wide=False):
    """One (type, value, sentence) holding exactly one sensitive value.

    `wide` (medium set) draws the sentence's number from a far larger range, so
    ~100,000 planted sentences in one file can all differ even for types with
    few possible values (diseases, medications).
    """
    city, state, _ = g.pick(IN_CITIES)
    kind = g.pick(["Email", "Phone", "Credit card", "Aadhaar", "PAN", "SSN", "IBAN", "Bank account", "Passport", "UPI ID",
                   "Disease", "Medication", "Date of birth", "Home address", "Person name", "Crypto wallet", "Voter ID",
                   "Driving licence", "GSTIN", "UK NI number"])
    p = g.person()
    value = {
        "Email": p["email"], "Phone": g.phone(g.pick(["IN", "US", "UK"])), "Credit card": g.card(),
        "Aadhaar": g.aadhaar(), "PAN": g.pan("P", p["last"]), "SSN": g.ssn(), "IBAN": g.iban(),
        "Bank account": g.account_no(), "Passport": g.passport_in(), "UPI ID": g.upi(p["first"]),
        "Disease": g.pick(DISEASES)[0], "Medication": g.pick(DRUGS), "Date of birth": fmt_d(p["dob"]),
        "Home address": g.address(g.pick(["IN", "US"])), "Person name": p["name"], "Crypto wallet": g.btc(),
        "Voter ID": g.voter_id(), "Driving licence": g.driving_licence(state), "GSTIN": g.gstin(state),
        "UK NI number": g.ni_number(),
    }[kind]
    n = _r(g, 2, 99_999) if wide else _r(g, 2, 40)
    sentence = {
        "Email": f"Corrections to note {n} can be sent to {value} before the next edition.",
        "Phone": f"The volunteer coordinator for week {n} can be reached on {value} in the evenings.",
        "Credit card": f"The club fee for season {n} was charged to credit card {value}, expiry {g.expiry()}.",
        "Aadhaar": f"The registration slip for camp {n} lists Aadhaar number {value} for the group leader.",
        "PAN": f"The donation receipt for drive {n} carries PAN {value} of the person who paid.",
        "SSN": f"The membership form for chapter {n} included SSN {value} by mistake.",
        "IBAN": f"Refunds for workshop {n} go to IBAN {value}.",
        "Bank account": f"The prize money for round {n} was sent to bank account number {value}.",
        "Passport": f"The permit for expedition {n} was issued against passport number {value}.",
        "UPI ID": f"Contributions for outing {n} were collected on UPI ID {value}.",
        "Disease": f"One participant in session {n} mentioned living with {value}.",
        "Medication": f"One participant in session {n} carried {value} as prescribed.",
        "Date of birth": f"The lost-property tag from event {n} showed a date of birth of {value}.",
        "Home address": f"Spare equipment from batch {n} is stored at {value}.",
        "Person name": f"The keys for shed {n} were handed over to {value}.",
        "Crypto wallet": f"The online raffle for meet {n} accepted coins at wallet address {value}.",
        "Voter ID": f"The venue booking for meet {n} was confirmed with voter ID {value}.",
        "Driving licence": f"The van for trip {n} was rented on driving licence {value}.",
        "GSTIN": f"The hall for gathering {n} was billed under GSTIN {value}.",
        "UK NI number": f"The volunteer pass for fixture {n} records National Insurance number {value}.",
    }[kind]
    return kind, value, sentence


# ----------------------------------------------------------------------------
def build_file(job):
    index, target, out_dir, max_items, density, per_kb = job
    medium = density == "medium"
    g = Gen(seed=(70_000 if medium else 50_000) + index)
    topic = TOPIC_ORDER[index % len(TOPIC_ORDER)]
    title, heading, make = TOPICS[topic]
    name = f"{index + 1:02d}_{topic}_{human(target)}.txt"
    path = os.path.join(out_dir, name)

    n_items = max(max_items + 1, round(target / 1024 * per_kb)) if medium else g.r.randint(1, max_items)
    at = sorted(g.r.uniform(0.02, 0.98) * target for _ in range(n_items))   # byte positions to plant at
    planted = []
    seen = set()
    redrawn = 0

    def unique_sentence(maker):
        nonlocal redrawn
        tries = 0
        while True:
            s = maker(g)
            if tries >= 3:
                # The topic's plain sentences are getting used up in this file:
                # widen the space with a log-style ending instead of looping.
                s = s[:-1] + g.pick(TRAILERS)(g)
            tries += 1
            keys = sentence_keys(s)
            if not BANNED.search(s) and not seen.intersection(keys):
                seen.update(keys)
                return s
            redrawn += 1

    written, section = 0, 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        header = f"{title.upper()}\n\n"
        fh.write(header)
        written += len(header.encode())
        while written < target:
            section += 1
            when = g.date_between(2025, 2026) + timedelta(days=section)
            sentences = [unique_sentence(make) for _ in range(g.r.randint(3, 7))]
            while at and written >= at[0]:
                at.pop(0)
                kind, value, s = plant(g, medium)
                while seen.intersection(sentence_keys(s)):
                    kind, value, s = plant(g, medium)
                seen.update(sentence_keys(s))
                sentences.insert(g.r.randint(0, len(sentences)), s)
                planted.append((kind, value))
            block = f"{heading} {section} - {when.strftime('%d %B %Y')}\n" + " ".join(sentences) + "\n\n"
            fh.write(block)
            written += len(block.encode("utf-8"))
        # Positions past the end (tiny files): plant into a closing paragraph.
        if at:
            closing = []
            for _ in at:
                kind, value, s = plant(g, medium)
                if medium:
                    while seen.intersection(sentence_keys(s)):
                        kind, value, s = plant(g, medium)
                    seen.update(sentence_keys(s))
                closing.append(s)
                planted.append((kind, value))
            block = " ".join(closing) + "\n"
            fh.write(block)
    write_answer_part(out_dir, index, name, planted)
    return {"file": name, "topic": title, "bytes": os.path.getsize(path), "sensitive_items": len(planted),
            "planted_values": type_counts(planted), "unique_sentences": len(seen)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--min-kb", type=float, default=2)
    ap.add_argument("--max-mb", type=float, default=100)
    ap.add_argument("--density", choices=["low", "medium"], default="low",
                    help="low: 1..--max-items values per file; medium: about --per-kb values per KB")
    ap.add_argument("--max-items", type=int, default=5, help="low: most sensitive values per file (each file gets 1..this)")
    ap.add_argument("--per-kb", type=float, default=1.0, help="medium: sensitive values per KB of text")
    ap.add_argument("--out", default=None, help="default: dlp_samples_low or dlp_samples_medium next to this script")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()
    args.out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), f"dlp_samples_{args.density}")

    os.makedirs(args.out, exist_ok=True)
    lo, hi = args.min_kb * 1024, args.max_mb * 2**20
    sizes = [int(lo * (hi / lo) ** (i / max(1, args.count - 1))) for i in range(args.count)]
    jobs = [(i, s, args.out, args.max_items, args.density, args.per_kb) for i, s in enumerate(sizes)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = sorted(pool.map(build_file, jobs), key=lambda r: r["file"])
    with open(os.path.join(args.out, "manifest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    merge_answer_parts(args.out)
    split_answer_key(args.out)
    total = sum(r["bytes"] for r in rows)
    print(f"{len(rows)} files, {total / 2**20:.0f} MB total, {sum(r['sensitive_items'] for r in rows)} planted values -> {args.out}")


if __name__ == "__main__":
    main()
