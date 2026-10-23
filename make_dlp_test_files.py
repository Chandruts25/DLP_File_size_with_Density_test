"""Generate realistic-looking .txt documents full of PII / PHI / PFI for the DLP.

Every value is synthetic (random names, made-up IDs), but each one is built the
way the real thing is — cards pass Luhn, Aadhaar passes Verhoeff, GSTIN and IBAN
carry correct check characters, BTC addresses are valid Base58Check — so the
detectors treat them as genuine.

No sentence is repeated within a file. Every prose sentence carries its own
specifics (names, dates, amounts, reference numbers), and each file keeps a set
of the sentences already written: a document that would repeat one is generated
again. Aligned form fields, table rows, log lines and code are layout, not
sentences, and are unique anyway because they carry the record's own values.

    python make_dlp_test_files.py                 # 50 files, 2 KB .. 100 MB, into ./dlp_samples_high
    python make_dlp_test_files.py --count 20 --max-mb 10 --out other_dir
"""
import argparse
import csv
import functools
import hashlib
import os
import random
import re
import string
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta

# ----------------------------------------------------------------------------
# Vocabulary
# ----------------------------------------------------------------------------
IN_FIRST = "Rajesh Priya Arjun Ananya Vikram Kavya Suresh Lakshmi Rahul Deepa Karthik Meera Anil Sneha Sanjay Pooja Ravi Divya Manoj Nisha Arun Swathi Ganesh Revathi Harish Keerthi Naveen Bhavana Prakash Aishwarya Dinesh Shalini Venkat Gayathri Mohan Ramya".split()
IN_LAST = "Kumar Sharma Iyer Reddy Nair Patel Gupta Singh Rao Menon Pillai Joshi Verma Krishnan Subramanian Chatterjee Das Mehta Bhat Naidu Agarwal Banerjee Kulkarni Shetty Hegde Murthy Saxena Mishra Kapoor Chandran".split()
US_FIRST = "James Mary Robert Jennifer Michael Linda William Elizabeth David Barbara Richard Susan Joseph Jessica Thomas Sarah Daniel Karen Matthew Nancy Andrew Lisa Brian Megan Kevin Rachel".split()
US_LAST = "Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Thompson White Harris Clark Lewis Young".split()
UK_FIRST = "Oliver Amelia Harry Isla George Ava Jack Emily Charlie Sophie Freddie Grace".split()
UK_LAST = "Wright Walker Hughes Edwards Green Hall Wood Clarke Turner Hill Baker Cooper".split()
FEMALE = set("Priya Ananya Kavya Lakshmi Deepa Meera Sneha Pooja Divya Nisha Swathi Revathi Keerthi Bhavana Aishwarya Shalini "
             "Gayathri Ramya Mary Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen Nancy Lisa Megan Rachel Amelia "
             "Isla Ava Emily Sophie Grace".split())

IN_CITIES = [("Chennai", "Tamil Nadu", "600"), ("Bengaluru", "Karnataka", "560"), ("Mumbai", "Maharashtra", "400"),
             ("Hyderabad", "Telangana", "500"), ("Pune", "Maharashtra", "411"), ("Kochi", "Kerala", "682"),
             ("New Delhi", "Delhi", "110"), ("Kolkata", "West Bengal", "700"), ("Coimbatore", "Tamil Nadu", "641"),
             ("Mysuru", "Karnataka", "570"), ("Madurai", "Tamil Nadu", "625"), ("Thiruvananthapuram", "Kerala", "695")]
IN_STREETS = "Anna Salai|MG Road|Nehru Street|Gandhi Nagar 2nd Cross|Lake View Road|Temple Street|Brigade Road|Linking Road|Banjara Hills Road No 12|Velachery Main Road|Residency Road|Park Street|Hill View Layout|Station Road".split("|")
US_CITIES = [("Springfield", "IL", "627"), ("Austin", "TX", "787"), ("Denver", "CO", "802"), ("Columbus", "OH", "432"),
             ("Raleigh", "NC", "276"), ("Portland", "OR", "972"), ("Madison", "WI", "537"), ("Tampa", "FL", "336")]
US_STREETS = "Oak Street|Maple Avenue|Pine Drive|Cedar Lane|Elm Court|Washington Blvd|Lakeview Terrace|Sunset Road|Birch Way|Hillcrest Drive".split("|")

DISEASES = [("Type 2 diabetes mellitus", "E11.9"), ("Essential hypertension", "I10"), ("Major depressive disorder, recurrent", "F33.1"),
            ("Chronic kidney disease, stage 3", "N18.3"), ("Asthma, moderate persistent", "J45.40"), ("HIV disease", "B20"),
            ("Hypothyroidism", "E03.9"), ("Coronary artery disease", "I25.10"), ("Rheumatoid arthritis", "M06.9"),
            ("Pulmonary tuberculosis", "A15.0"), ("Chronic hepatitis B", "B18.1"), ("Generalized anxiety disorder", "F41.1"),
            ("Iron deficiency anaemia", "D50.9"), ("Migraine without aura", "G43.009"), ("COPD", "J44.9"), ("Dengue fever", "A90"),
            ("Bipolar affective disorder", "F31.9"), ("Epilepsy", "G40.909"), ("Psoriasis", "L40.0"), ("Gout", "M10.9")]
DRUGS = ["Metformin 500 mg BD", "Telmisartan 40 mg OD", "Sertraline 50 mg OD", "Atorvastatin 20 mg HS", "Levothyroxine 75 mcg OD",
         "Amlodipine 5 mg OD", "Insulin glargine 18 units SC at bedtime", "Salbutamol inhaler 2 puffs PRN", "Pantoprazole 40 mg OD",
         "Tenofovir/Emtricitabine 1 tab OD", "Methotrexate 15 mg weekly", "Clopidogrel 75 mg OD", "Escitalopram 10 mg OD",
         "Ferrous sulphate 200 mg TDS", "Rifampicin 450 mg OD", "Paracetamol 650 mg SOS", "Azithromycin 500 mg OD x 3 days",
         "Lithium carbonate 300 mg BD", "Levetiracetam 500 mg BD", "Allopurinol 100 mg OD"]
SYMPTOMS = ["fatigue and intermittent fever", "breathlessness on exertion", "chest discomfort radiating to the left arm",
            "polyuria and weight loss", "persistent dry cough", "pedal oedema and reduced urine output", "low mood and poor sleep",
            "joint pain and morning stiffness", "high-grade fever with body ache", "recurrent headaches with vomiting",
            "palpitations and dizziness", "abdominal pain and loose stools"]
DOCTORS = ["Dr. S. Raman, MD (Internal Medicine)", "Dr. Anita Desai, DM (Cardiology)", "Dr. K. Venkatesh, MS (General Surgery)",
           "Dr. Emily Carter, MD", "Dr. Farhan Qureshi, DNB (Nephrology)", "Dr. Lakshmi Narayan, MD (Psychiatry)",
           "Dr. Rohan Mehra, MD (Pulmonology)", "Dr. Grace Okafor, MD (Endocrinology)"]
HOSPITALS = ["Apollo Speciality Hospital", "Sri Ramachandra Medical Centre", "Fortis Memorial Hospital", "St. Mary's Regional Medical Center",
             "Kauvery Hospital", "Manipal Hospital", "Mercy General Hospital", "Aster CMI Hospital", "MIOT International"]
LABS = ["METROPOLIS HEALTHCARE", "THYROCARE TECHNOLOGIES", "QUEST DIAGNOSTICS", "DR. LAL PATHLABS", "VIJAYA DIAGNOSTIC CENTRE"]
COMPANIES = ["Zentrix Software Pvt Ltd", "Bluepeak Analytics LLP", "Northwind Retail India Pvt Ltd", "Kaveri Textiles Ltd",
             "Orion Health Systems Inc.", "Granite Logistics Pvt Ltd", "Lumen Fintech Solutions Pvt Ltd", "Sapphire Foods Pvt Ltd",
             "Vertex Pharma Ltd", "Monsoon Media Pvt Ltd", "Ironbridge Infra Ltd", "Pinewood Consulting LLP"]
DESIGNATIONS = ["Senior Software Engineer", "Data Analyst", "Accounts Executive", "Operations Manager", "HR Business Partner",
                "Product Manager", "Customer Support Lead", "Staff Nurse", "Sales Officer", "DevOps Engineer", "Finance Controller",
                "Business Analyst", "QA Engineer", "Branch Manager"]
DEGREES = ["B.Tech (Computer Science), Anna University", "MBA (Finance), Symbiosis Institute of Business Management",
           "B.Com, University of Mumbai", "M.Sc (Statistics), University of Hyderabad", "BSc Nursing, Manipal Academy",
           "B.E. (ECE), Visvesvaraya Technological University", "MCA, Bharathiar University", "BA Economics, Delhi University",
           "BS Accounting, Ohio State University", "MSc Data Science, University of Leeds"]
BANKS = [("SBIN", "State Bank of India"), ("HDFC", "HDFC Bank"), ("ICIC", "ICICI Bank"), ("UTIB", "Axis Bank"),
         ("KKBK", "Kotak Mahindra Bank"), ("PUNB", "Punjab National Bank"), ("IDIB", "Indian Bank"), ("CNRB", "Canara Bank")]
UPI_HANDLES = ["okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "paytm", "ibl", "axl"]
MERCHANTS = ["Swiggy", "Amazon Pay", "BigBasket", "Tata Power", "Airtel Postpaid", "Zomato", "Flipkart", "IRCTC", "BESCOM",
             "Reliance Digital", "Uber India", "Apollo Pharmacy", "LIC Premium", "Jio Recharge", "Myntra", "Decathlon", "Croma"]
INSURERS = ["Star Health and Allied Insurance", "HDFC ERGO General Insurance", "Blue Cross Blue Shield", "Aetna", "UnitedHealthcare",
            "ICICI Lombard", "Niva Bupa Health Insurance", "Cigna"]
SUPPORT_BRANDS = ["Lumen Pay", "QuickCart", "ShieldCard", "MetroBank", "FreshBasket", "TravelNest", "PayZen"]
STATE_CODES = {"Tamil Nadu": "33", "Karnataka": "29", "Maharashtra": "27", "Telangana": "36", "Kerala": "32", "Delhi": "07", "West Bengal": "19"}
RTO = {"Tamil Nadu": "TN", "Karnataka": "KA", "Maharashtra": "MH", "Telangana": "TS", "Kerala": "KL", "Delhi": "DL", "West Bengal": "WB"}

# ----------------------------------------------------------------------------
# Identifiers built with their real check rules
# ----------------------------------------------------------------------------
_VD = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
       [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_VP = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],
       [4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
_VINV = [0,4,3,2,1,5,6,7,8,9]
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_GST = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def fmt_d(d):
    return d.strftime("%d/%m/%Y")


def field(label, value):
    """One aligned form line, e.g. `Patient Name        : Ravi Kumar`."""
    return f"{label:<22}: {value}"


class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)

    def pick(self, seq):
        return self.r.choice(seq)

    def digits(self, n, first_nonzero=False):
        s = "".join(self.r.choice(string.digits) for _ in range(n))
        return (self.r.choice("123456789") + s[1:]) if first_nonzero else s

    def letters(self, n):
        return "".join(self.r.choice(string.ascii_uppercase) for _ in range(n))

    def ref(self, n=8):
        return self.digits(n, first_nonzero=True)

    def date_between(self, y0, y1):
        return date(y0, 1, 1) + timedelta(days=self.r.randint(0, (date(y1, 12, 31) - date(y0, 1, 1)).days))

    def when(self):
        return datetime(2025, 1, 1) + timedelta(seconds=self.r.randint(0, 60_000_000))

    def money_in(self, lo, hi):
        s = str(self.r.randint(lo, hi))
        if len(s) > 3:
            head, tail = s[:-3], s[-3:]
            head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
            s = f"{head},{tail}"
        return f"₹{s}"

    def money_us(self, lo, hi):
        return f"${self.r.randint(lo, hi):,}.{self.r.randint(0, 99):02d}"

    # -- people / contact ------------------------------------------------------
    def person(self, region=None):
        region = region or self.pick(["IN", "IN", "IN", "US", "US", "UK"])
        first, last = {"IN": (IN_FIRST, IN_LAST), "US": (US_FIRST, US_LAST), "UK": (UK_FIRST, UK_LAST)}[region]
        first, last = self.pick(first), self.pick(last)
        female = first in FEMALE
        return {"region": region, "first": first, "last": last, "name": f"{first} {last}",
                "dob": self.date_between(1948, 2004), "gender": "Female" if female else "Male",
                "he": "she" if female else "he", "his": "her" if female else "his", "He": "She" if female else "He",
                "His": "Her" if female else "His", "email": self.email(first, last), "phone": self.phone(region),
                "address": self.address(region)}

    def email(self, first, last):
        dom = self.pick(["gmail.com", "yahoo.co.in", "outlook.com", "hotmail.com", "rediffmail.com", "icloud.com", "protonmail.com"])
        return f"{first.lower()}{self.pick(['.', '_', ''])}{last.lower()}{self.r.randint(1, 9999)}@{dom}"

    def phone(self, region):
        if region == "IN":
            n = self.pick("6789") + self.digits(9)
            return self.pick([f"+91 {n[:5]} {n[5:]}", f"+91-{n}", f"{n[:5]} {n[5:]}"])
        if region == "US":
            return f"({self.r.randint(201, 989)}) {self.r.randint(201, 999)}-{self.digits(4)}"
        return f"+44 7{self.digits(3)} {self.digits(6)}"

    def address(self, region):
        if region == "IN":
            city, state, pin = self.pick(IN_CITIES)
            return f"No. {self.r.randint(1, 450)}, {self.pick(IN_STREETS)}, {city}, {state} - {pin}{self.digits(3)}"
        if region == "US":
            city, st, z = self.pick(US_CITIES)
            return f"{self.r.randint(100, 9999)} {self.pick(US_STREETS)}, Apt {self.r.randint(1, 60)}, {city}, {st} {z}{self.digits(2)}"
        return (f"{self.r.randint(1, 180)} {self.pick(['Church Road', 'High Street', 'Victoria Avenue', 'Park Lane', 'Mill Lane'])}, "
                f"{self.pick(['Leeds', 'Bristol', 'Manchester', 'Reading', 'York'])} {self.letters(2)}{self.r.randint(1, 20)} {self.r.randint(1, 9)}{self.letters(2)}")

    # -- checksummed IDs -----------------------------------------------------
    def card(self, spaced=None):
        prefix = self.pick(["4", "4", "51", "52", "53", "54", "55"])
        body = prefix + self.digits(15 - len(prefix))
        total = 0
        for i, ch in enumerate(reversed(body)):
            d = int(ch)
            if i % 2 == 0:
                d *= 2
                d = d - 9 if d > 9 else d
            total += d
        num = body + str((10 - total % 10) % 10)
        spaced = self.r.random() < 0.6 if spaced is None else spaced
        return " ".join(num[i:i + 4] for i in range(0, 16, 4)) if spaced else num

    def expiry(self):
        return f"{self.r.randint(1, 12):02d}/{self.r.randint(27, 32)}"

    def aadhaar(self):
        body = self.pick("23456789") + self.digits(10)
        c = 0
        for i, ch in enumerate(reversed(body)):
            c = _VD[c][_VP[(i + 1) % 8][int(ch)]]
        num = body + str(_VINV[c])
        return f"{num[:4]} {num[4:8]} {num[8:]}"

    def pan(self, holder="P", surname="K"):
        return self.letters(3) + holder + surname[0].upper() + self.digits(4) + self.letters(1)

    def gstin(self, state="Tamil Nadu"):
        base = STATE_CODES.get(state, "33") + self.pan(holder=self.pick("CF"), surname=self.letters(1)) + self.pick("123456789") + "Z"
        total = 0
        for i, ch in enumerate(base):
            p = _GST.index(ch) * (2 if i % 2 else 1)
            total += p // 36 + p % 36
        return base + _GST[(36 - total % 36) % 36]

    def ifsc(self, code=None):
        return (code or self.pick(BANKS)[0]) + "0" + self.digits(6)

    def iban(self, country=None):
        country = country or self.pick(["GB", "DE"])
        bban = (self.letters(4) + self.digits(14)) if country == "GB" else self.digits(18)
        num = int("".join(str(int(c, 36)) for c in bban + country + "00"))
        iban = f"{country}{98 - num % 97:02d}{bban}"
        return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))

    def swift(self):
        return self.letters(4) + self.pick(["IN", "GB", "US", "DE", "SG"]) + self.letters(2) + self.pick(["", "XXX"])

    def ssn(self):
        a = self.r.randint(1, 899)
        a = 667 if a == 666 else a
        return f"{a:03d}-{self.r.randint(1, 99):02d}-{self.r.randint(1, 9999):04d}"

    def ni_number(self):
        first, second = self.pick("ABCEGHJKLMNOPRSTWXYZ"), self.pick("ABCEGHJKLMNPRSTWXYZ")
        if first + second in ("BG", "GB", "KN", "NK", "NT", "TN", "ZZ"):
            first, second = "A", "B"
        return f"{first}{second} {self.digits(2)} {self.digits(2)} {self.digits(2)} {self.pick('ABCD')}"

    def btc(self):
        payload = b"\x00" + bytes(self.r.getrandbits(8) for _ in range(20))
        raw = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        n, out = int.from_bytes(raw, "big"), ""
        while n:
            n, rem = divmod(n, 58)
            out = _B58[rem] + out
        return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + out

    def eth(self):
        return "0x" + "".join(self.r.choice("0123456789abcdef") for _ in range(40))

    def voter_id(self):
        return self.letters(3) + self.digits(7, first_nonzero=True)

    def passport_in(self):
        return self.pick("ABCDEFGHJKLMNPRSTUVWY") + self.digits(7, first_nonzero=True)

    def driving_licence(self, state="Tamil Nadu"):
        return f"{RTO.get(state, 'TN')}{self.r.randint(1, 72):02d} {self.r.randint(2005, 2023)}{self.digits(7, True)}"

    def vehicle(self, state="Tamil Nadu"):
        return f"{RTO.get(state, 'TN')} {self.r.randint(1, 72):02d} {self.letters(2)} {self.digits(4, True)}"

    def upi(self, first):
        return f"{first.lower()}{self.digits(self.r.randint(2, 4))}@{self.pick(UPI_HANDLES)}"

    def account_no(self):
        return self.digits(self.r.choice([11, 12, 14, 15]), first_nonzero=True)

    def abha(self):
        return f"{self.digits(2, True)}-{self.digits(4)}-{self.digits(4)}-{self.digits(4)}"

    def mrn(self):
        return f"MRN-{self.digits(7, True)}"

    def ip(self):
        return f"{self.r.randint(11, 223)}.{self.r.randint(0, 255)}.{self.r.randint(0, 255)}.{self.r.randint(1, 254)}"

    def token(self, n=32):
        return "".join(self.r.choice(string.ascii_letters + string.digits) for _ in range(n))


# ----------------------------------------------------------------------------
# Documents. Every prose sentence names its own specifics, so it is unique.
# ----------------------------------------------------------------------------
def discharge_summary(g):
    p = g.person(g.pick(["IN", "IN", "US"]))
    age = 2026 - p["dob"].year
    adm = g.date_between(2025, 2026)
    dis = adm + timedelta(days=g.r.randint(2, 14))
    dx = g.r.sample(DISEASES, 2)
    meds = g.r.sample(DRUGS, 4)
    hosp, doc, ins = g.pick(HOSPITALS), g.pick(DOCTORS), g.pick(INSURERS)
    ip_no = f"IP/{adm.year}/{g.ref(6)}"
    since = g.r.randint(max(1960, p["dob"].year + 12), 2024)
    weeks = g.r.randint(1, 6)
    lines = [
        hosp.upper(), "DISCHARGE SUMMARY", "",
        field("Patient Name", f"{p['name']}       Gender: {p['gender']}"),
        field("Date of Birth", f"{fmt_d(p['dob'])}       Age: {age} years"),
        field("Patient ID", f"{g.mrn()}       IP No: {ip_no}"),
        field("ABHA Number", g.abha()),
        field("Address", p["address"]),
        field("Contact No", f"{p['phone']}       Email: {p['email']}"),
        field("Admitted / Discharged", f"{fmt_d(adm)}  /  {fmt_d(dis)}"),
        field("Consultant", doc),
        field("Insurance", f"{ins}   Policy No. {g.letters(2)}{g.digits(10, True)}   Member ID {g.letters(3)}{g.digits(9)}"),
        "", "FINAL DIAGNOSIS",
        f"  1. {dx[0][0]} ({dx[0][1]})",
        f"  2. {dx[1][0]} ({dx[1][1]})",
        "", "HISTORY OF PRESENT ILLNESS",
        g.pick([
            f"{p['name']}, a {age}-year-old {p['gender'].lower()}, presented to the {g.pick(['emergency department', 'outpatient clinic', 'casualty'])} on {fmt_d(adm)} with {g.r.randint(2, 21)} days of {g.pick(SYMPTOMS)}.",
            f"On {fmt_d(adm)}, {p['name']} ({age} years) was brought in by {p['his']} {g.pick(['son', 'daughter', 'spouse', 'brother', 'neighbour'])} after {g.r.randint(2, 21)} days of {g.pick(SYMPTOMS)}.",
        ]) + " " + g.pick([
            f"{p['first']} has been a known case of {dx[0][0]} since {since} and was {g.pick(['on irregular treatment', 'lost to follow-up', 'controlled on oral agents', 'reviewed last at ' + g.pick(HOSPITALS)])} until {g.pick(['last month', 'early ' + str(adm.year), 'the previous admission'])}.",
            f"{dx[0][0]} was first diagnosed in {since}, and {p['first']} reports {g.pick(['missing doses', 'stopping medication', 'good adherence', 'switching doctors'])} over the last {g.r.randint(2, 24)} months.",
        ]),
        f"{p['first']} denies travel outside {g.pick(IN_CITIES + US_CITIES)[0]} in the {g.r.randint(2, 12)} weeks before {fmt_d(adm)}, and family history includes {g.pick(DISEASES)[0]} in the {g.pick(['mother', 'father', 'elder sister', 'paternal uncle', 'grandmother'])} (diagnosed {g.r.randint(1975, 2022)}).",
        "", "INVESTIGATIONS",
        f"Hb {g.r.randint(85, 160) / 10} g/dL | TLC {g.r.randint(3500, 16000)} /cumm | Platelets {g.r.randint(80, 450)}x10^3 | "
        f"HbA1c {g.r.randint(52, 120) / 10}% | Creatinine {g.r.randint(6, 45) / 10} mg/dL | TSH {g.r.randint(4, 110) / 10} mIU/L | "
        f"Chest X-ray: {g.pick(['clear lung fields', 'mild cardiomegaly', 'right lower zone infiltrates', 'bilateral hilar prominence'])}",
        "", "HOSPITAL COURSE",
        f"During admission {ip_no}, {p['first']} received {g.pick(['IV fluids and empirical antibiotics', 'IV insulin infusion', 'nebulisation and steroids', 'diuretics and fluid restriction', 'antipyretics and platelet monitoring'])} for {g.r.randint(1, 9)} days.",
        g.pick([
            f"Psychiatry reviewed {p['name']} on {fmt_d(adm + timedelta(days=1))} and started counselling with {g.pick(DRUGS)}.",
            f"Nephrology opinion on {fmt_d(adm + timedelta(days=1))} advised {p['first']} to avoid NSAIDs and repeat creatinine in {g.r.randint(1, 4)} weeks.",
            f"An echocardiogram on {fmt_d(adm + timedelta(days=1))} showed an ejection fraction of {g.r.randint(30, 65)}% for {p['first']}.",
            f"Blood sugars for {p['first']} settled on a basal-bolus regimen by day {g.r.randint(2, 7)} of admission {ip_no}.",
        ]),
        f"At discharge on {fmt_d(dis)}, {p['first']} was {g.pick(['stable, afebrile and ambulant', 'haemodynamically stable', 'symptomatically better', 'tolerating oral diet'])} with a pulse of {g.r.randint(62, 104)}/min.",
        "", "MEDICATIONS ON DISCHARGE",
        *[f"  - {m}" for m in meds],
        "", "FOLLOW-UP",
        f"{p['first']} should return to the OPD on {fmt_d(dis + timedelta(weeks=weeks))} with fasting and post-prandial sugar reports, quoting {ip_no}.",
        f"In an emergency the family can reach the {hosp} helpline on {g.phone(p['region'])}.",
        "", f"Signed: {doc}      Date: {fmt_d(dis)}",
    ]
    return "\n".join(lines) + "\n"


def lab_report(g):
    p = g.person()
    d = g.date_between(2025, 2026)
    acc = f"ACC{g.ref(9)}"
    dx = g.pick(DISEASES)[0]
    return "\n".join([
        f"{g.pick(LABS)} - LABORATORY REPORT",
        field("Patient", f"{p['name']}    Age/Sex: {2026 - p['dob'].year}/{p['gender'][0]}    DOB: {fmt_d(p['dob'])}"),
        field("Patient ID", f"{g.mrn()}    Accession: {acc}"),
        field("Collected", f"{fmt_d(d)} {g.r.randint(6, 11):02d}:{g.r.randint(0, 59):02d}    Referred by: {g.pick(DOCTORS)}"),
        field("Phone", p["phone"]),
        "",
        f"{'TEST':<26}{'RESULT':<14}{'UNITS':<10}REFERENCE",
        f"{'Fasting Blood Glucose':<26}{g.r.randint(70, 260):<14}{'mg/dL':<10}70-100",
        f"{'HbA1c':<26}{g.r.randint(48, 125) / 10:<14}{'%':<10}< 5.7",
        f"{'Total Cholesterol':<26}{g.r.randint(130, 300):<14}{'mg/dL':<10}< 200",
        f"{'HIV 1 & 2 Antibodies':<26}{g.pick(['Non-reactive', 'Non-reactive', 'Reactive']):<14}{'':<10}Non-reactive",
        f"{'HBsAg':<26}{g.pick(['Negative', 'Negative', 'Positive']):<14}{'':<10}Negative",
        f"{'Serum Creatinine':<26}{g.r.randint(5, 40) / 10:<14}{'mg/dL':<10}0.7-1.3",
        "",
        f"Impression for {p['name']} ({acc}): the profile is consistent with {dx}, and clinical correlation is advised by {g.pick(['Dr. M. Iqbal', 'Dr. R. Sen', 'Dr. P. Thomas', 'Dr. N. Bose'])} on {fmt_d(d)}.",
    ]) + "\n"


def bank_statement(g, n_txn=None):
    p = g.person("IN")
    code, bank = g.pick(BANKS)
    acct = g.account_no()
    start = g.date_between(2025, 2026)
    bal = g.r.randint(5000, 900000)
    rows = []
    for i in range(n_txn or g.r.randint(12, 40)):
        d = start + timedelta(days=i // 2)
        if g.r.random() < 0.3:
            amt = g.r.randint(2000, 150000)
            bal += amt
            desc = g.pick([f"NEFT CR-{g.pick(COMPANIES).upper()[:16]}-SAL-{g.ref(6)}", f"UPI/CR/{g.digits(12)}/{g.upi(g.pick(IN_FIRST))}",
                           f"IMPS/{g.digits(12)}/REFUND", f"INT.PD:{g.ref(6)}"])
            rows.append(f"{fmt_d(d)}  {desc[:48]:<48} {'':>12} {amt:>12,.2f} {bal:>14,.2f}")
        else:
            amt = g.r.randint(50, min(40000, max(60, bal)))
            bal -= amt
            desc = g.pick([f"UPI/DR/{g.digits(12)}/{g.pick(MERCHANTS)}/{g.upi(g.pick(IN_FIRST))}", f"POS {g.digits(4)} {g.pick(MERCHANTS).upper()} {g.ref(6)}",
                           f"ACH D- {g.pick(['HDFC LTD HOME LOAN', 'BAJAJ FINANCE EMI', 'ICICI PRU LIFE'])} {g.ref(6)}", f"ATM WDL {g.pick(IN_CITIES)[0].upper()} {g.digits(6)}"])
            rows.append(f"{fmt_d(d)}  {desc[:48]:<48} {amt:>12,.2f} {'':>12} {bal:>14,.2f}")
    gen = g.when()
    return "\n".join([
        bank.upper(), "STATEMENT OF ACCOUNT", "",
        field("Account Holder", p["name"].upper()),
        field("Address", p["address"]),
        field("Account Number", f"{acct}    Type: {g.pick(['Savings', 'Salary Savings', 'Current'])}"),
        field("IFSC / MICR", f"{g.ifsc(code)}  /  {g.digits(9, True)}"),
        field("Customer ID", f"{g.digits(9, True)}    Registered Mobile: {p['phone']}"),
        field("Email", p["email"]),
        field("Debit Card", f"{g.card()}    valid thru {g.expiry()}"),
        field("Statement Period", f"{fmt_d(start)} to {fmt_d(start + timedelta(days=30))}"),
        "",
        f"DATE        {'NARRATION':<48} {'WITHDRAWAL':>12} {'DEPOSIT':>12} {'BALANCE':>14}",
        *rows, "",
        field("Closing Balance", f"{bal:,.2f}"),
        f"This statement for account ending {acct[-4:]} was generated on {gen:%d/%m/%Y at %H:%M:%S} and needs no signature.",
    ]) + "\n"


def kyc_form(g):
    p = g.person("IN")
    city, state, _ = g.pick(IN_CITIES)
    code, bank = g.pick(BANKS)
    ref = f"KYC/{g.ref(9)}"
    signed = g.date_between(2025, 2026)
    return "\n".join([
        f"CUSTOMER KYC APPLICATION FORM    Ref: {ref}", "",
        field("1. Full Name", p["name"]),
        field("2. Father's Name", f"{g.pick([n for n in IN_FIRST if n not in FEMALE])} {p['last']}"),
        field("3. Date of Birth", fmt_d(p["dob"])),
        field("4. Gender", f"{p['gender']}    Marital Status: {g.pick(['Married', 'Single', 'Married', 'Divorced', 'Widowed'])}"),
        field("5. Aadhaar Number", g.aadhaar()),
        field("6. PAN", g.pan("P", p["last"])),
        field("7. Voter ID (EPIC)", g.voter_id()),
        field("8. Passport Number", f"{g.passport_in()}    Valid till: {fmt_d(g.date_between(2027, 2035))}"),
        field("9. Driving Licence", g.driving_licence(state)),
        field("10. Mobile", p["phone"]),
        field("11. Email", p["email"]),
        field("12. Address", p["address"]),
        field("13. Occupation", f"{g.pick(DESIGNATIONS)}, {g.pick(COMPANIES)}"),
        field("14. Annual Income", g.money_in(300000, 4500000)),
        field("15. Bank Account", f"{bank}    A/c {g.account_no()}    IFSC {g.ifsc(code)}"),
        field("16. UPI ID", g.upi(p["first"])),
        field("17. Vehicle Reg. No", g.vehicle(state)),
        "",
        f"Declaration: I, {p['name']}, confirm on {fmt_d(signed)} that the particulars in application {ref} are true and complete.",
        f"Place: {city}      Date: {fmt_d(signed)}      Signature: {p['first'][0]}. {p['last']}",
    ]) + "\n"


def payslip(g):
    p = g.person("IN")
    co = g.pick(COMPANIES)
    code, bank = g.pick(BANKS)
    basic = g.r.randint(25000, 180000)
    hra, spl = basic // 2, g.r.randint(5000, 60000)
    pf, pt, tds = basic * 12 // 100, 200, g.r.randint(0, 45000)
    gross = basic + hra + spl
    month = g.date_between(2025, 2026)
    acct = g.account_no()
    return "\n".join([
        co, f"PAYSLIP FOR {month:%B %Y}".upper(), "",
        field("Employee Name", f"{p['name']}    Employee ID: EMP{g.ref(6)}"),
        field("Designation", f"{g.pick(DESIGNATIONS)}    Department: {g.pick(['Engineering', 'Finance', 'Operations', 'Sales', 'HR'])}"),
        field("Date of Joining", f"{fmt_d(g.date_between(2012, 2024))}    Location: {g.pick(IN_CITIES)[0]}"),
        field("PAN / UAN", f"{g.pan('P', p['last'])}  /  {g.digits(12, True)}"),
        field("PF Account No", f"{g.letters(2)}/{g.letters(3)}/{g.digits(7)}/000/{g.digits(7)}"),
        field("Bank", f"{bank}    A/c {acct}    IFSC {g.ifsc(code)}"),
        "",
        f"{'EARNINGS':<20}{'':>10}    {'DEDUCTIONS':<20}{'':>10}",
        f"{'Basic':<20}{basic:>10,}    {'Provident Fund':<20}{pf:>10,}",
        f"{'HRA':<20}{hra:>10,}    {'Professional Tax':<20}{pt:>10,}",
        f"{'Special Allowance':<20}{spl:>10,}    {'Income Tax (TDS)':<20}{tds:>10,}",
        f"{'Gross Earnings':<20}{gross:>10,}    {'Total Deductions':<20}{pf + pt + tds:>10,}",
        "",
        f"Net pay of Rs. {gross - pf - pt - tds:,} for {month:%B %Y} was credited to {p['first']}'s account ending {acct[-4:]}.",
    ]) + "\n"


def hr_record(g):
    p = g.person(g.pick(["IN", "IN", "UK", "US"]))
    em = g.person(p["region"])
    ids = {"IN": [field("PAN", g.pan("P", p["last"])), field("Aadhaar", g.aadhaar())],
           "UK": [field("National Insurance No", g.ni_number())],
           "US": [field("SSN", g.ssn())]}[p["region"]]
    joined = g.date_between(2012, 2025)
    ctc = g.money_in(450000, 4800000) if p["region"] == "IN" else g.money_us(48000, 210000)
    return "\n".join([
        f"EMPLOYEE MASTER RECORD - CONFIDENTIAL    ({g.letters(2)}{g.ref(6)})",
        field("Employee", f"{p['name']}    Status: {g.pick(['Active', 'Active', 'On notice', 'Long leave'])}"),
        field("Date of Birth", f"{fmt_d(p['dob'])}    Gender: {p['gender']}"),
        field("Marital Status", g.pick(["Married", "Single", "Married, 2 children", "Separated", "Widowed"])),
        *ids,
        field("Home Address", p["address"]),
        field("Personal Email", f"{p['email']}    Mobile: {p['phone']}"),
        field("Role", f"{g.pick(DESIGNATIONS)}, {g.pick(COMPANIES)}    Joined: {fmt_d(joined)}"),
        field("Previous Employer", f"{g.pick(COMPANIES)}    {g.r.randint(2004, 2011)}-{joined.year}"),
        field("Education", f"{g.pick(DEGREES)}, {g.r.randint(1995, 2018)}"),
        field("Annual CTC", f"{ctc}    Last rating: {g.pick(['Exceeds', 'Meets', 'Meets', 'Below'])}"),
        field("Emergency Contact", f"{em['name']} ({g.pick(['spouse', 'father', 'sister', 'mother', 'brother'])})    {em['phone']}"),
        "",
        g.pick([
            f"{p['first']} declared {g.pick(DISEASES)[0]} to HR on {fmt_d(g.date_between(2024, 2026))}, and a flexible schedule was approved by {em['first']} {g.pick(US_LAST + IN_LAST)}.",
            f"{p['first']} took {g.r.randint(10, 90)} days of medical leave from {fmt_d(g.date_between(2024, 2026))} for {g.pick(['spinal surgery', 'cancer treatment', 'a cardiac procedure', 'maternity', 'depression'])}.",
            f"No medical conditions were declared by {p['name']} at the last review on {fmt_d(g.date_between(2024, 2026))}.",
        ]),
    ]) + "\n"


def gst_invoice(g):
    city, state, _ = g.pick(IN_CITIES)
    seller, buyer = g.r.sample(COMPANIES, 2)
    code, bank = g.pick(BANKS)
    inv = f"INV/{g.r.randint(24, 26)}-{g.r.randint(25, 27)}/{g.ref(6)}"
    items, total = [], 0
    for _ in range(g.r.randint(2, 6)):
        qty, rate = g.r.randint(1, 50), g.r.randint(250, 45000)
        total += qty * rate
        name = g.pick(['Laptop service AMC', 'Cloud hosting (monthly)', 'Office chairs', 'Cotton fabric rolls', 'Annual software licence',
                       'Consulting hours', 'Printer cartridges', 'Network switches'])
        items.append(f"{name:<32}{g.digits(4, True)}   {qty:>4}  {rate:>10,}  {qty * rate:>12,}")
    tax = total * 18 // 100
    due = g.date_between(2025, 2026)
    return "\n".join([
        f"TAX INVOICE                                   Invoice No: {inv}",
        seller, g.address("IN"),
        field("GSTIN", f"{g.gstin(state)}    PAN: {g.pan('C', seller)}"),
        "",
        field("Bill To", buyer),
        field("Buyer GSTIN", f"{g.gstin(g.pick(list(STATE_CODES)))}    Place of supply: {state}"),
        field("Invoice Date", fmt_d(due - timedelta(days=30))),
        "",
        f"{'DESCRIPTION':<32}{'HSN':<7}{'QTY':>4}  {'RATE':>10}  {'AMOUNT':>12}",
        *items,
        f"{'':<45}Taxable value : {total:>12,}",
        f"{'':<45}IGST @18%     : {tax:>12,}",
        f"{'':<45}TOTAL         : {total + tax:>12,}",
        "",
        f"Please pay Rs. {total + tax:,} against {inv} by {fmt_d(due)} to {bank} current account {g.account_no()} (IFSC {g.ifsc(code)}) or UPI {g.pick(['payments', 'accounts', 'billing'])}.{seller.split()[0].lower()}@{g.pick(UPI_HANDLES)}.",
    ]) + "\n"


def email_msg(g):
    a, b = g.person(), g.person()
    when = g.when()
    ref = g.ref(7)
    bodies = [
        (f"Reimbursement claim {ref}", [
            f"Hi {b['first']},",
            f"As discussed on {fmt_d(when.date())}, here are my details for reimbursement claim {ref}.",
            f"I paid {g.money_in(1200, 85000)} with card {g.card()} (expiry {g.expiry()}) at {g.pick(MERCHANTS)}.",
            f"Please refund it to account {g.account_no()} at IFSC {g.ifsc()} in the name of {a['name']}.",
        ]),
        (f"Documents for visa file {ref}", [
            f"Hello {b['first']},",
            f"Sharing the details you asked for on {fmt_d(when.date())} for visa file {ref}.",
            f"My passport number is {g.passport_in()}, date of birth {fmt_d(a['dob'])}, and PAN {g.pan('P', a['last'])}.",
            f"The address on record for {a['name']} is {a['address']}.",
        ]),
        (f"Leave update for {a['first']} ({ref})", [
            f"Hi {b['first']},",
            f"{a['first']} was diagnosed with {g.pick(DISEASES)[0]} on {fmt_d(when.date())} and has started {g.pick(DRUGS)}.",
            f"The doctor at {g.pick(HOSPITALS)} has advised {a['first']} to take {g.r.randint(5, 30)} days of rest from {fmt_d(when.date() + timedelta(days=1))}.",
            f"{a['His']} backup contact during leave {ref} is {a['phone']}.",
        ]),
        (f"Advance payment {ref}", [
            f"Dear {b['first']},",
            f"Please send the advance of {g.money_us(500, 20000)} for contract {ref} to my wallet {g.btc()}.",
            f"If crypto is not possible, the ETH address {g.eth()} or UPI {g.upi(a['first'])} works too.",
            f"For the 1099 form, {a['name']}'s SSN is {g.ssn()} and the mailing address is {a['address']}.",
        ]),
        (f"Salary revision letter {ref}", [
            f"Hi {b['first']},",
            f"Your revised CTC under letter {ref} is {g.money_in(600000, 5200000)} per annum from {fmt_d(when.date())}.",
            f"Your PF UAN {g.digits(12, True)} stays the same, and salary will go to account {g.account_no()}.",
            f"Please sign and return the letter to {a['name']} by {fmt_d(when.date() + timedelta(days=g.r.randint(3, 15)))}.",
        ]),
    ]
    subject, body = g.pick(bodies)
    return "\n".join([
        f"From: {a['name']} <{a['email']}>",
        f"To: {b['name']} <{b['email']}>",
        f"Date: {when:%a, %d %b %Y %H:%M:%S} +0530",
        f"Subject: {g.pick(['', 'Re: ', 'FW: '])}{subject}",
        "",
        body[0], "", " ".join(body[1:]), "",
        "Regards,", a["name"],
        f"{g.pick(DESIGNATIONS)} | {g.pick(COMPANIES)} | Mobile: {a['phone']}",
    ]) + "\n"


def support_chat(g):
    c = g.person("IN")
    agent = g.pick(["Ritu", "Mohan", "Sara", "Imran", "Divya", "Joel", "Asha", "Vinod"])
    brand = g.pick(SUPPORT_BRANDS)
    ticket = g.ref(9)
    t = g.when()
    issue = g.pick(["my card got blocked after a failed payment", "I was charged twice for order", "I need to update my KYC for order",
                    "my refund has not arrived for order", "the delivery for order never reached me, order"])
    order = g.ref(10)
    amt = g.money_in(299, 45000)
    turns = [
        (agent, f"Hi {c['first']}, thanks for contacting {brand} support about ticket {ticket}; how can I help today?"),
        (c["first"], f"Hi {agent}, {issue} {order} worth {amt}."),
        (agent, f"Sorry about order {order}, {c['first']} - could you confirm the mobile number and date of birth on the account?"),
        (c["first"], f"Mobile is {c['phone']} and DOB {fmt_d(c['dob'])}."),
        (agent, f"Thanks. Please share the card used for order {order} so I can trace the {amt} payment."),
        (c["first"], f"It's {g.card()}, expiry {g.expiry()}."),
        (agent, f"Got it. Where should the {amt} refund for ticket {ticket} go, a bank account or UPI?"),
        (c["first"], f"UPI {g.upi(c['first'])} please, or account {g.account_no()} with IFSC {g.ifsc()}."),
        (agent, f"Our records show Aadhaar ending {g.digits(4)} for {c['name']}; can you confirm your PAN to finish KYC on ticket {ticket}?"),
        (c["first"], f"PAN is {g.pan('P', c['last'])}, and my new address is {g.address('IN')}."),
        (agent, f"All updated, {c['first']}. The refund of {amt} on ticket {ticket} should reach you by {fmt_d(t.date() + timedelta(days=g.r.randint(3, 9)))}."),
    ]
    out = [f"=== {brand} chat transcript {ticket} ==="]
    for who, msg in turns:
        t += timedelta(seconds=g.r.randint(15, 240))
        out.append(f"[{t:%Y-%m-%d %H:%M:%S}] {who}: {msg}")
    out.append(f"=== End of chat {ticket} ===")
    return "\n".join(out) + "\n"


def tax_return(g):
    p = g.person("US")
    sp_first = g.pick([n for n in US_FIRST if (n in FEMALE) != (p["first"] in FEMALE)])
    wages = g.r.randint(38000, 240000)
    year = g.r.randint(2023, 2025)
    return "\n".join([
        f"Form 1040 - U.S. Individual Income Tax Return {year} - working copy for {p['name']} ({g.ref(6)})",
        field("Filing status", g.pick(["Married filing jointly", "Single", "Head of household", "Married filing separately"])),
        field("Taxpayer", f"{p['first']} {p['last']}    SSN: {g.ssn()}"),
        field("Spouse", f"{sp_first} {p['last']}    SSN: {g.ssn()}"),
        field("Home address", p["address"]),
        field("Dependent", f"{g.pick(US_FIRST)} {p['last']}    SSN: {g.ssn()}    Relationship: {g.pick(['son', 'daughter'])}"),
        field("1  Wages (W-2)", f"{wages:,}"),
        field("2b Taxable interest", f"{g.r.randint(0, 4000):,}"),
        field("11 Adjusted gross inc.", f"{wages + g.r.randint(0, 9000):,}"),
        field("Direct deposit", f"routing {g.digits(9, True)}    account {g.account_no()}    type: Checking"),
        field("Contact", f"{g.phone('US')}    {p['email']}"),
    ]) + "\n"


def loan_application(g):
    p = g.person("IN")
    city, state, _ = g.pick(IN_CITIES)
    co = g.person("IN")
    return "\n".join([
        f"HOME LOAN APPLICATION - {g.pick(['HDFC Ltd', 'LIC Housing Finance', 'SBI Home Loans', 'Bajaj Housing Finance'])}    No: HL{g.ref(9)}",
        field("Branch", city),
        field("Applicant", f"{p['name']}    DOB: {fmt_d(p['dob'])}"),
        field("PAN / Aadhaar", f"{g.pan('P', p['last'])}  /  {g.aadhaar()}"),
        field("Co-applicant", f"{co['name']}    PAN: {g.pan('P', co['last'])}    Relation: {g.pick(['Spouse', 'Father', 'Brother'])}"),
        field("Employer", f"{g.pick(COMPANIES)}    {g.pick(DESIGNATIONS)}"),
        field("Net monthly income", g.money_in(45000, 380000)),
        field("Loan requested", f"{g.money_in(1500000, 12000000)}    {g.r.randint(10, 30)} years @ {g.r.randint(830, 975) / 100}% p.a."),
        field("Existing loans", g.pick([f"Car loan, EMI {g.money_in(9000, 32000)}", f"Personal loan, outstanding {g.money_in(80000, 600000)}", "None"])),
        field("CIBIL score", str(g.r.randint(640, 860))),
        field("Property", f"Flat {g.r.randint(101, 1504)}, {g.pick(['Prestige', 'Sobha', 'Casagrand', 'Lodha', 'Brigade'])} {g.pick(['Lakeside', 'Meadows', 'Habitat', 'Heights', 'Orchards'])}, {city}, {state}"),
        field("Salary account", f"{g.account_no()}    IFSC {g.ifsc()}"),
        field("Contact", f"{p['phone']}    {p['email']}"),
    ]) + "\n"


def crypto_kyc(g):
    p = g.person()
    gov = g.pick([("PAN", g.pan("P", p["last"])), ("Passport", g.passport_in()), ("SSN", g.ssn())])
    return "\n".join([
        f"EXCHANGE ACCOUNT VERIFICATION - {g.pick(['CoinDCX', 'WazirX', 'Binance', 'Kraken'])}    Case {g.ref(8)}",
        field("User", f"{p['name']}    {p['email']}"),
        field("Phone / DOB", f"{p['phone']}  /  {fmt_d(p['dob'])}"),
        field(gov[0], gov[1]),
        field("BTC withdrawal", g.btc()),
        field("BTC withdrawal", g.btc()),
        field("ETH withdrawal", g.eth()),
        field("Last login", f"{g.ip()}    {g.pick(['iPhone 14', 'Pixel 8', 'Samsung S23', 'Windows 11 / Chrome'])}"),
        field("Linked bank", f"A/c {g.account_no()}    IFSC {g.ifsc()}"),
        field("Monthly volume", g.money_in(20000, 4000000)),
    ]) + "\n"


def intl_wire(g):
    p = g.person("UK")
    return "\n".join([
        f"INTERNATIONAL PAYMENT INSTRUCTION    Ref {g.ref(10)}",
        field("Remitter", f"{p['name']}, {p['address']}"),
        field("Remitter IBAN", f"{g.iban('GB')}    BIC: {g.swift()}"),
        field("Beneficiary", g.person("IN")["name"]),
        field("Beneficiary bank", f"{g.pick(BANKS)[1]}    SWIFT {g.swift()}    A/c {g.account_no()}    IFSC {g.ifsc()}"),
        field("Intermediary IBAN", g.iban("DE")),
        field("Amount", f"GBP {g.r.randint(500, 48000):,}.00    Purpose: {g.pick(['Family maintenance', 'Tuition fees', 'Property purchase', 'Medical treatment'])}"),
        field("NI number (HMRC)", g.ni_number()),
    ]) + "\n"


def meeting_notes(g):
    people = g.r.sample(IN_FIRST + US_FIRST, 4)
    d = g.date_between(2025, 2026)
    lines = [
        f"Meeting notes - {g.pick(['Q3 planning', 'Sprint retro', 'Vendor review', 'Board prep', 'Incident review'])} ({fmt_d(d)}, {g.r.randint(9, 18)}:{g.pick(['00', '30'])})",
        f"Attendees: {', '.join(people)}",
        f"- Revenue for the quarter ending {fmt_d(d)} was {g.r.randint(3, 40)}% above plan, and {people[0]} reported {g.r.randint(3, 40)} new accounts in {g.pick(IN_CITIES)[0]}.",
        f"- The acquisition of {g.pick(COMPANIES)} at a valuation of {g.money_in(50000000, 900000000)} stays confidential until the board meets on {fmt_d(d + timedelta(days=g.r.randint(5, 40)))}.",
        f"- {people[1]} said the data platform migration slips to {fmt_d(d + timedelta(days=g.r.randint(10, 60)))} because of a {g.r.randint(2, 6)}-week vendor delay.",
        f"- Action for {people[2]}: share pricing model v{g.r.randint(2, 9)}.{g.r.randint(0, 9)} by {fmt_d(d + timedelta(days=g.r.randint(2, 9)))}, and {people[3]} will chase legal on NDA {g.ref(6)}.",
    ]
    if g.r.random() < 0.4:
        fn = g.pick(["fetch_customers", "load_accounts", "sync_payments", "export_patients", "pull_invoices"])
        table = g.pick(["customers", "accounts", "payments", "patients", "invoices"])
        lines += [
            f"{people[0]} pasted this config on {fmt_d(d)}; it must move to the vault before release {g.r.randint(10, 99)}.{g.r.randint(0, 9)}.",
            "```python",
            "import requests",
            "",
            f'API_KEY = "sk_live_{g.token(28)}"',
            f'DB_URL = "postgresql://admin:{g.token(12)}@10.{g.r.randint(0, 255)}.{g.r.randint(0, 255)}.{g.r.randint(1, 254)}:5432/{table}"',
            "",
            f"def {fn}(region, page_size={g.pick([50, 100, 200, 500])}):",
            f'    url = f"https://api.{g.pick(["internal", "corp", "intra"])}.example/v{g.r.randint(1, 3)}/{table}?region={{region}}&size={{page_size}}"',
            f'    resp = requests.get(url, headers={{"Authorization": f"Bearer {{API_KEY}}"}}, timeout={g.pick([10, 20, 30, 60])})',
            "    resp.raise_for_status()",
            "    return resp.json()",
            "```",
        ]
    return "\n".join(lines) + "\n"


def app_log_block(g, lines=40):
    out = []
    t = g.when()
    svc = g.pick(["payments", "kyc", "auth", "ehr", "gateway", "orders"])
    for _ in range(lines):
        t += timedelta(milliseconds=g.r.randint(5, 4000))
        p = g.person()
        lvl = g.pick(["INFO", "INFO", "INFO", "DEBUG", "WARN", "ERROR"])
        msg = g.pick([
            f"POST /api/v1/payments status=201 user={p['email']} card_last4={g.digits(4)} amount={g.r.randint(10, 90000)} ip={g.ip()}",
            f"KYC verified user_id={g.ref(8)} pan={g.pan('P', p['last'])} aadhaar=\"{g.aadhaar()}\"",
            f"Payment failed card={g.card(spaced=False)} reason={g.pick(['INSUFFICIENT_FUNDS', 'DO_NOT_HONOUR', 'EXPIRED_CARD'])} customer=\"{p['name']}\"",
            f"OTP sent to {p['phone']} session={g.token(24)}",
            f"Login success username={p['first'].lower()}{g.digits(3)} ip={g.ip()} device_id={g.token(16)}",
            f"Address updated for \"{p['name']}\": {p['address']}",
            f"Refund initiated upi={g.upi(p['first'])} amount={g.r.randint(50, 20000)} ref={g.ref(10)}",
            f"GET /health status=200 latency_ms={g.r.randint(1, 30)} req_id={g.token(12)}",
            f"Slow query {g.r.randint(500, 9000)}ms table=customer_profiles query_id={g.token(10)}",
            f"Patient record viewed mrn={g.mrn()} by={g.pick(US_FIRST).lower()} dx=\"{g.pick(DISEASES)[0]}\"",
        ])
        out.append(f"{t:%Y-%m-%d %H:%M:%S},{t.microsecond // 1000:03d} {lvl} [{svc}-svc] {msg}")
    return "\n".join(out) + "\n"


def crm_export_rows(g, rows=50):
    out = []
    for _ in range(rows):
        p = g.person()
        out.append(" | ".join([g.ref(8), p["name"], fmt_d(p["dob"]), p["email"], p["phone"], p["address"],
                                g.pick([f"PAN {g.pan('P', p['last'])}", f"SSN {g.ssn()}", f"Aadhaar {g.aadhaar()}", f"NI {g.ni_number()}"]),
                                f"card {g.card()}", g.pick(["Gold", "Silver", "Platinum"])]))
    return "\n".join(out) + "\n"


# Each file is one kind of real-world artefact.
THEMES = {
    "discharge_summary":   ("Hospital discharge summaries", [discharge_summary, lab_report]),
    "bank_statement":      ("Bank statement export", [bank_statement]),
    "kyc_batch":           ("KYC applications batch", [kyc_form]),
    "payroll":             ("Payroll payslips", [payslip]),
    "hr_records":          ("HR employee master records", [hr_record]),
    "gst_invoices":        ("GST tax invoices", [gst_invoice]),
    "mailbox_export":      ("Mailbox export", [email_msg]),
    "support_chats":       ("Customer support chat transcripts", [support_chat]),
    "tax_returns":         ("US tax return working copies", [tax_return]),
    "loan_applications":   ("Home loan applications", [loan_application]),
    "crypto_kyc":          ("Crypto exchange KYC", [crypto_kyc, intl_wire]),
    "app_logs":            ("Application logs", [app_log_block]),
    "crm_export":          ("CRM customer export", [crm_export_rows]),
    "shared_drive_dump":   ("Mixed shared-drive dump", [discharge_summary, bank_statement, kyc_form, payslip, email_msg,
                                                         support_chat, gst_invoice, meeting_notes, hr_record, loan_application]),
}
THEME_ORDER = list(THEMES)

# ----------------------------------------------------------------------------
# Sentence uniqueness
# ----------------------------------------------------------------------------
_ABBR = re.compile(r"\b(Dr|No|Mr|Mrs|Ms|St|Pvt|Ltd|Inc|Rs|vs|Jr|Sr|Apt|Tech|Com|Sc|E)\.")
_INITIAL = re.compile(r"\b([A-Z])\.(?=\s)")
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_WORD = re.compile(r"[A-Za-z]{2,}")


def sentence_keys(line):
    """Hashes of the sentences on one line; layout lines (aligned forms, tables,
    log lines, code, CSV-style rows) are not sentences and return []."""
    if "  " in line or line.count(" | ") >= 2 or not line.strip():
        return []
    text = _INITIAL.sub(r"\1", _ABBR.sub(r"\1", line.strip()))
    keys = []
    for frag in _SPLIT.split(text):
        words = _WORD.findall(frag)
        if len(words) >= 4 and (frag.rstrip()[-1:] in ".!?" or len(words) >= 7):
            keys.append(hash(" ".join(frag.lower().split())))
    return keys


# ----------------------------------------------------------------------------
# Answer key: every sensitive value the generator writes
# ----------------------------------------------------------------------------
# Each ID builder is wrapped to note what it returned (no extra random calls, so
# the files are unchanged). After a document is final, only the values that
# actually appear in its text are kept: a card whose last 4 digits alone are
# printed, or a person whose email is never shown, does not count.
_RECORDED = {"card": "Credit card", "aadhaar": "Aadhaar", "pan": "PAN", "gstin": "GSTIN", "ifsc": "IFSC code",
             "iban": "IBAN", "swift": "SWIFT/BIC", "ssn": "SSN", "ni_number": "UK NI number", "btc": "Crypto wallet",
             "eth": "Crypto wallet", "voter_id": "Voter ID", "passport_in": "Passport", "driving_licence": "Driving licence",
             "vehicle": "Vehicle registration", "upi": "UPI ID", "account_no": "Bank account", "abha": "ABHA number",
             "mrn": "Patient ID (MRN)", "ip": "IP address", "email": "Email", "phone": "Phone", "address": "Home address"}
_NO_NESTED = {"gstin"}          # a GSTIN embeds a PAN: count the GSTIN only


def _recording(method, kind):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        parent = getattr(self, "_inside", None)
        self._inside = method.__name__
        try:
            value = method(self, *args, **kwargs)
        finally:
            self._inside = parent
        if getattr(self, "record", None) is not None and parent not in _NO_NESTED:
            self.record.append((kind, value))
        return value
    return wrapper


for _name, _kind in _RECORDED.items():
    setattr(Gen, _name, _recording(getattr(Gen, _name), _kind))

_plain_person = Gen.person


def _recording_person(self, region=None):
    p = _plain_person(self, region)
    if getattr(self, "record", None) is not None:
        self.record += [("Person name", p["name"]), ("Date of birth", fmt_d(p["dob"]))]
    return p


Gen.person = _recording_person
_HEALTH = [("Disease", d) for d, _ in DISEASES] + [("Medication", m) for m in DRUGS]


def values_in(text, recorded):
    """The recorded values that really appear in `text`, plus every disease and
    medication name it mentions (one entry per occurrence)."""
    out, kept = [], set()
    for kind, value in recorded:
        if (isinstance(value, str) and value and (kind, value) not in kept
                and (value in text or (kind == "Person name" and value.upper() in text))):
            kept.add((kind, value))
            out.append((kind, value))
    for kind, value in _HEALTH:
        out += [(kind, value)] * text.count(value)
    return out


def type_counts(planted):
    counts = {}
    for kind, _ in planted:
        counts[kind] = counts.get(kind, 0) + 1
    return " ; ".join(f"{k}: {c}" for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def write_answer_part(out_dir, index, name, planted):
    with open(os.path.join(out_dir, f".answer_{index:02d}.csv"), "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows((name, k, v) for k, v in planted)


def merge_answer_parts(out_dir):
    """Join the per-file parts into answer_key.csv (file, type, value)."""
    parts = sorted(f for f in os.listdir(out_dir) if f.startswith(".answer_"))
    with open(os.path.join(out_dir, "answer_key.csv"), "w", newline="", encoding="utf-8") as out:
        csv.writer(out).writerow(["file", "type", "value"])
        for part in parts:
            with open(os.path.join(out_dir, part), encoding="utf-8") as fh:
                out.write(fh.read())
            os.remove(os.path.join(out_dir, part))


EXCEL_ROWS = 1_000_000     # Excel shows at most 1,048,576 rows per sheet


def split_answer_key(out_dir):
    """answer_key.csv -> answer_key/<file>.csv, one per sample file, so each opens in
    Excel. A file with more than EXCEL_ROWS values is split into _part1, _part2 ..."""
    folder = os.path.join(out_dir, "answer_key")
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):
        os.remove(os.path.join(folder, old))
    by_file = {}
    with open(os.path.join(out_dir, "answer_key.csv"), encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        next(reader)
        for name, kind, value in reader:
            by_file.setdefault(name, []).append((kind, value))
    for name, rows in by_file.items():
        stem = os.path.splitext(name)[0]
        chunks = [rows[i:i + EXCEL_ROWS] for i in range(0, len(rows), EXCEL_ROWS)]
        for n, chunk in enumerate(chunks, 1):
            suffix = f"_part{n}" if len(chunks) > 1 else ""
            with open(os.path.join(folder, f"{stem}{suffix}.csv"), "w", newline="", encoding="utf-8") as out:
                w = csv.writer(out)
                w.writerow(["type", "value"])
                w.writerows(chunk)
    return len(by_file)


def human(n):
    return f"{n / 2**20:.0f}MB" if n >= 2**20 else f"{max(1, round(n / 1024))}KB"


def build_file(job):
    index, target, out_dir = job
    g = Gen(seed=1000 + index)
    theme = THEME_ORDER[index % len(THEME_ORDER)]
    title, makers = THEMES[theme]
    name = f"{index + 1:02d}_{theme}_{human(target)}.txt"
    path = os.path.join(out_dir, name)
    seen = set()
    planted = []
    docs = written = retries = dropped = 0
    sep = "\n" + "-" * 78 + "\n\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        if theme == "crm_export":
            header = "customer_id | name | dob | email | phone | address | government_id | payment_card | tier\n"
            fh.write(header)
            written += len(header.encode())
        while written < target:
            for attempt in range(10):
                g.record = []
                lines = g.pick(makers)(g).split("\n")
                per_line = [sentence_keys(line) for line in lines]
                keys = [k for ks in per_line for k in ks]
                if len(set(keys)) == len(keys) and not seen.intersection(keys):
                    break
                retries += 1
            else:
                # Still clashing after 10 tries: drop the clashing lines rather than repeat them.
                kept, local = [], set()
                for line, ks in zip(lines, per_line):
                    if any(k in seen or k in local for k in ks):
                        dropped += 1
                        continue
                    local.update(ks)
                    kept.append(line)
                lines, keys = kept, list(local)
            seen.update(keys)
            doc = "\n".join(lines)
            planted += values_in(doc, g.record)
            if theme not in ("app_logs", "crm_export") and written:
                doc = sep + doc
            fh.write(doc)
            written += len(doc.encode("utf-8"))
            docs += 1
    write_answer_part(out_dir, index, name, planted)
    return {"file": name, "topic": title, "bytes": os.path.getsize(path), "sensitive_items": len(planted),
            "planted_values": type_counts(planted), "unique_sentences": len(seen)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--min-kb", type=float, default=2)
    ap.add_argument("--max-mb", type=float, default=100)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "dlp_samples_high"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    lo, hi = args.min_kb * 1024, args.max_mb * 2**20
    sizes = [int(lo * (hi / lo) ** (i / max(1, args.count - 1))) for i in range(args.count)]
    jobs = [(i, s, args.out) for i, s in enumerate(sizes)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = sorted(pool.map(build_file, jobs), key=lambda r: r["file"])
    with open(os.path.join(args.out, "manifest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    merge_answer_parts(args.out)
    split_answer_key(args.out)
    total = sum(r["bytes"] for r in rows)
    print(f"{len(rows)} files, {total / 2**20:.0f} MB total, {sum(r['sensitive_items'] for r in rows)} sensitive values -> {args.out}")


if __name__ == "__main__":
    main()
