"""Canonical ICP title taxonomy for Xoxoday, derived from ABM_Campaign_Planner_v2.

The planner carries 206 raw persona strings across Empuls / Loyalife / Plum. Many are
fragments ("site", "manager", "brand", "Zonal") or near-duplicates ("Comp & Benefits" /
"Comp & Benefits manager" / "Comp & benefits team"). This module collapses them into 60
canonical title families.

Each family carries:
  key       - stable slug
  label     - human name
  products  - which Xoxoday product(s) sell into it
  role      - buyer | champion | influencer  (per the planner's use-case column)
  variants  - title strings to pass to Apollo person_titles[] (Apollo does substring
              matching on normalised titles, so these are deliberately broad)
  seats     - expected in-ICP contacts per account at the 1000-4999 employee reference
              band; scaled by SIZE_MULT elsewhere
"""

# Buying-center headcount grows sublinearly with company size. Multipliers are relative
# to the 1000-4999 reference band that `seats` is expressed in.
SIZE_MULT = {
    "200-499": 0.30,
    "500-999": 0.55,
    "1000-4999": 1.00,
    "5000-9999": 2.00,
    "10000+": 4.00,
}

FAMILIES = [
    # ------------------------------------------------------------------ EMPULS
    # HR / People / Total Rewards buying center. Horizontal across industries.
    dict(key="chro", label="CHRO / Chief People Officer", products=["Empuls"], role="buyer", seats=1.0,
         variants=["chief human resources officer", "chief people officer", "chief hr officer",
                   "chief human capital officer", "chro", "cpo human resources"]),
    dict(key="vp_hr", label="VP HR / VP People", products=["Empuls"], role="buyer", seats=1.6,
         variants=["vp human resources", "vice president human resources", "vp people",
                   "vice president people", "svp human resources", "vp people operations"]),
    dict(key="hr_director", label="HR Director / Head of HR", products=["Empuls"], role="buyer", seats=2.6,
         variants=["hr director", "director human resources", "head of hr",
                   "head of human resources", "human resources head", "director of people"]),
    dict(key="hr_manager", label="HR Manager", products=["Empuls"], role="champion", seats=4.2,
         variants=["hr manager", "human resources manager", "people manager",
                   "senior hr manager", "hr lead"]),
    dict(key="hrbp", label="HRBP / People Partner", products=["Empuls"], role="champion", seats=4.0,
         variants=["hr business partner", "hrbp", "people business partner",
                   "senior hr business partner", "people partner"]),
    dict(key="hr_ops", label="HR Ops / People Ops", products=["Empuls"], role="influencer", seats=3.2,
         variants=["hr operations", "people operations", "hr ops", "people ops",
                   "hr operations manager", "head of people operations", "hr administrator"]),
    dict(key="total_rewards", label="Head of Total Rewards", products=["Empuls", "Plum"], role="buyer", seats=1.0,
         variants=["total rewards", "head of total rewards", "director total rewards",
                   "vp total rewards", "total rewards manager"]),
    dict(key="comp_ben", label="Compensation & Benefits", products=["Empuls"], role="buyer", seats=2.1,
         variants=["compensation and benefits", "compensation & benefits", "comp and benefits",
                   "head of compensation", "compensation manager", "benefits manager",
                   "head of benefits", "benefits director"]),
    dict(key="employee_experience", label="Head of Employee Experience", products=["Empuls"], role="buyer", seats=1.1,
         variants=["employee experience", "head of employee experience",
                   "director employee experience", "ex lead", "employee experience manager"]),
    dict(key="engagement", label="Head of Employee Engagement", products=["Empuls"], role="champion", seats=1.1,
         variants=["employee engagement", "head of employee engagement",
                   "engagement manager", "employee engagement manager"]),
    dict(key="internal_comms", label="Head of Internal Communications", products=["Empuls"], role="champion", seats=1.5,
         variants=["internal communications", "head of internal communications",
                   "corporate communications manager", "internal comms",
                   "employee communications"]),
    dict(key="wellbeing", label="Head of Wellbeing / Wellness", products=["Empuls", "Plum"], role="champion", seats=1.0,
         variants=["wellbeing", "well-being", "head of wellness", "wellness manager",
                   "employee wellbeing", "wellness program manager"]),
    dict(key="people_analytics", label="People Analytics Lead", products=["Empuls"], role="influencer", seats=1.0,
         variants=["people analytics", "hr analytics", "head of people analytics",
                   "workforce analytics"]),
    dict(key="people_culture", label="People & Culture Lead", products=["Empuls"], role="buyer", seats=1.5,
         variants=["people and culture", "people & culture", "head of people and culture",
                   "director people and culture", "culture manager"]),
    dict(key="payroll", label="Payroll Head", products=["Empuls"], role="influencer", seats=1.0,
         variants=["payroll head", "head of payroll", "payroll manager",
                   "payroll director", "global payroll"]),
    dict(key="learning", label="Head of L&D", products=["Empuls", "Plum"], role="champion", seats=1.5,
         variants=["learning and development", "head of l&d", "l&d manager",
                   "head of learning", "talent development"]),
    dict(key="cfo", label="CFO / Finance Head", products=["Empuls", "Plum"], role="buyer", seats=1.4,
         variants=["chief financial officer", "cfo", "finance director", "head of finance",
                   "vp finance", "financial controller"]),
    dict(key="finance_ops", label="Finance Ops / AP Lead", products=["Plum"], role="influencer", seats=1.8,
         variants=["finance operations", "accounts payable manager", "ap lead",
                   "head of accounts payable", "finance ops manager"]),
    dict(key="coo_ops", label="COO / Head of Operations", products=["Empuls", "Plum"], role="buyer", seats=2.2,
         variants=["chief operating officer", "coo", "head of operations",
                   "operations director", "vp operations", "operations head"]),
    dict(key="procurement", label="Procurement Head", products=["Empuls", "Plum"], role="influencer", seats=1.6,
         variants=["procurement head", "head of procurement", "procurement manager",
                   "chief procurement officer", "sourcing manager", "vendor manager"]),
    dict(key="it_lead", label="IT Lead / CIO", products=["Empuls"], role="influencer", seats=2.0,
         variants=["chief information officer", "cio", "head of it", "it director",
                   "it manager"]),
    dict(key="sales_comp", label="CRO / VP Sales / RevOps / Sales Comp", products=["Empuls", "Plum"], role="buyer", seats=3.4,
         variants=["chief revenue officer", "cro", "vp sales", "vice president of sales",
                   "head of sales", "revenue operations", "revops", "sales operations",
                   "sales compensation", "incentive compensation manager"]),

    # ---------------------------------------------------------------- LOYALIFE
    # Loyalty / CRM / trade-marketing buying center. Concentrated in BFSI, retail,
    # telco, airlines, hospitality, auto, fuel, gaming, healthcare-payer.
    dict(key="cmo", label="CMO", products=["Loyalife", "Plum"], role="buyer", seats=1.0,
         variants=["chief marketing officer", "cmo", "chief growth officer"]),
    dict(key="cco_commercial", label="Chief Commercial / Customer Officer", products=["Loyalife"], role="buyer", seats=1.1,
         variants=["chief commercial officer", "cco", "chief customer officer",
                   "chief revenue and commercial officer"]),
    dict(key="cdo_digital", label="Chief Digital Officer / Head of Digital", products=["Loyalife"], role="buyer", seats=1.6,
         variants=["chief digital officer", "head of digital", "digital director",
                   "vp digital", "digital transformation head"]),
    dict(key="loyalty_head", label="VP / Head of Loyalty", products=["Loyalife"], role="buyer", seats=1.4,
         variants=["head of loyalty", "vp loyalty", "vice president loyalty",
                   "director of loyalty", "gm loyalty", "loyalty head",
                   "loyalty programme manager", "loyalty program manager"]),
    dict(key="loyalty_ops", label="Loyalty Manager / Loyalty Ops", products=["Loyalife"], role="champion", seats=2.4,
         variants=["loyalty manager", "loyalty operations", "loyalty marketing manager",
                   "loyalty specialist", "loyalty analyst"]),
    dict(key="crm_head", label="Head of CRM / CRM Manager", products=["Loyalife", "Plum"], role="buyer", seats=2.2,
         variants=["head of crm", "crm director", "crm manager", "vp crm",
                   "crm marketing manager"]),
    dict(key="growth_head", label="Head of Growth", products=["Loyalife", "Plum"], role="buyer", seats=1.6,
         variants=["head of growth", "vp growth", "growth director", "growth lead",
                   "director of growth"]),
    dict(key="retention", label="Head of Retention / Retention Manager", products=["Loyalife"], role="champion", seats=1.5,
         variants=["head of retention", "retention manager", "retention marketing",
                   "churn manager", "customer retention"]),
    dict(key="lifecycle", label="Lifecycle Marketing", products=["Loyalife", "Plum"], role="champion", seats=1.8,
         variants=["lifecycle marketing", "lifecycle manager", "head of lifecycle",
                   "lifecycle marketing manager", "crm lifecycle"]),
    dict(key="rewards_prog", label="Head of Rewards / Rewards Manager", products=["Loyalife"], role="champion", seats=1.5,
         variants=["head of rewards", "rewards manager", "rewards program manager",
                   "rewards product manager", "cards rewards manager"]),
    dict(key="cards_banking", label="Head of Cards / Retail Banking Lines", products=["Loyalife"], role="buyer", seats=2.6,
         variants=["head of cards", "cards head", "credit cards head", "digital banking head",
                   "head of retail banking", "head of retail assets", "head of wealth",
                   "head of sme banking", "business banking head", "priority banking"]),
    dict(key="membership", label="Head of Membership", products=["Loyalife"], role="buyer", seats=1.0,
         variants=["head of membership", "membership director", "membership manager",
                   "subscription product manager", "head of subscriptions"]),
    dict(key="cvm_customer", label="Head of Customer / CVM Lead", products=["Loyalife"], role="buyer", seats=1.6,
         variants=["head of customer", "customer value management", "cvm",
                   "head of customer engagement", "customer marketing head",
                   "head of consumer"]),
    dict(key="partnerships", label="Head of Partnerships / Partner Marketing", products=["Loyalife", "Plum"], role="buyer", seats=2.0,
         variants=["head of partnerships", "partnerships director", "partner marketing",
                   "partner program manager", "alliances manager", "affiliate manager",
                   "offers and partnerships"]),
    dict(key="channel", label="Head of Channel / Distribution", products=["Loyalife"], role="buyer", seats=2.2,
         variants=["head of channel", "channel head", "channel marketing manager",
                   "head of distribution", "distribution head", "partner channel manager",
                   "agent network manager", "dsa channel manager"]),
    dict(key="trade_marketing", label="Trade Marketing (National / Regional / Zonal)", products=["Loyalife"], role="champion", seats=3.0,
         variants=["trade marketing", "head of trade marketing", "trade marketing manager",
                   "national trade marketing", "regional trade marketing",
                   "zonal marketing manager", "shopper marketing"]),
    dict(key="retail_media", label="Head of Retail / Retail Media", products=["Loyalife"], role="buyer", seats=1.4,
         variants=["head of retail", "retail media", "retail media network",
                   "head of retail media", "rmn lead", "merchant marketing manager",
                   "head of merchant business"]),
    dict(key="regional_sales", label="Regional / Zonal Sales Head", products=["Loyalife"], role="champion", seats=4.0,
         variants=["regional sales head", "regional sales manager", "zonal sales manager",
                   "area sales manager", "regional business head", "zonal head"]),
    dict(key="ffp_airline", label="FFP / Frequent Flyer Program Manager", products=["Loyalife"], role="champion", seats=0.9,
         variants=["frequent flyer", "ffp manager", "mileage program", "loyalty and ffp",
                   "frequent flyer program manager"]),
    dict(key="aftermarket_auto", label="Aftermarket / Dealer Network (Auto)", products=["Loyalife"], role="buyer", seats=1.8,
         variants=["head of aftermarket", "aftermarket manager", "regional dealer manager",
                   "dealer development", "aftersales head"]),
    dict(key="specification", label="Head of Specification (Building Materials)", products=["Loyalife"], role="buyer", seats=1.0,
         variants=["head of specification", "specification manager",
                   "specification sales manager", "retail education manager"]),
    dict(key="patient_exp", label="Head of Patient Experience", products=["Loyalife", "Plum"], role="buyer", seats=1.0,
         variants=["patient experience", "head of patient experience",
                   "patient engagement", "patient experience manager"]),
    dict(key="liveops_gaming", label="Live-Ops / Monetization / VIP (Gaming)", products=["Loyalife", "Plum"], role="buyer", seats=2.0,
         variants=["live ops", "liveops", "live operations manager", "head of monetization",
                   "monetization manager", "vip manager", "player engagement"]),

    # -------------------------------------------------------------------- PLUM
    # Rewards & incentives infrastructure. Broadest, most cross-functional.
    dict(key="vp_marketing", label="VP / Head of Marketing", products=["Plum"], role="buyer", seats=2.4,
         variants=["vp marketing", "vice president marketing", "head of marketing",
                   "marketing director", "senior director marketing"]),
    dict(key="demand_gen", label="Demand Gen / ABM / Field / Performance Marketing", products=["Plum"], role="champion", seats=3.6,
         variants=["demand generation", "head of demand gen", "abm manager",
                   "account based marketing", "field marketing", "performance marketing",
                   "growth marketing manager", "marketing operations"]),
    dict(key="events", label="Head of Events / Event Marketing Manager", products=["Plum"], role="champion", seats=1.8,
         variants=["head of events", "event marketing manager", "events manager",
                   "event director", "head of field and events"]),
    dict(key="customer_success", label="Head of Customer Success", products=["Plum"], role="buyer", seats=2.0,
         variants=["head of customer success", "vp customer success", "customer success director",
                   "chief customer officer", "customer success manager"]),
    dict(key="promotions", label="Promotions / Member Engagement", products=["Plum"], role="champion", seats=1.6,
         variants=["promotions manager", "member engagement", "consumer promotions",
                   "sales promotion manager"]),
    dict(key="research_insights", label="VP Insights / Research Director / Panel Ops", products=["Plum"], role="buyer", seats=2.2,
         variants=["vp insights", "head of insights", "research director",
                   "consumer insights", "market research manager", "research operations",
                   "panel manager", "ux research", "head of user research"]),
    dict(key="community", label="Head of Community / Community Manager", products=["Plum"], role="champion", seats=1.4,
         variants=["head of community", "community manager", "community director",
                   "developer community"]),
    dict(key="product_payments", label="CPO / Product Ops / Payments PM", products=["Plum", "Loyalife"], role="buyer", seats=2.6,
         variants=["chief product officer", "head of product", "product operations",
                   "payments product manager", "head of payments", "vp product"]),
    dict(key="program_mgmt", label="Program Manager / Program Coordinator", products=["Plum"], role="champion", seats=3.0,
         variants=["program manager", "programme manager", "program coordinator",
                   "project manager operations"]),
    dict(key="claims_insurance", label="Head of Claims / Claims Ops", products=["Plum"], role="buyer", seats=1.6,
         variants=["head of claims", "claims operations", "claims manager", "claims director"]),
    dict(key="clinical_trials", label="Clinical Ops / Trial Coordinator", products=["Plum"], role="buyer", seats=2.0,
         variants=["clinical operations", "clinical trial manager", "trial coordinator",
                   "clinical research manager", "head of clinical operations"]),
    dict(key="legal_ops", label="Legal Ops / Settlement Administrator", products=["Plum"], role="influencer", seats=1.2,
         variants=["legal operations", "legal ops manager", "settlement administrator",
                   "claims administrator"]),
    dict(key="resident_exp", label="Resident Experience Manager (Real Estate)", products=["Plum"], role="buyer", seats=1.2,
         variants=["resident experience", "resident services manager",
                   "community experience manager", "tenant experience"]),
    dict(key="sdr_leadership", label="SDR Leadership", products=["Plum"], role="champion", seats=1.6,
         variants=["head of sdr", "sdr manager", "director of sales development",
                   "bdr manager", "sales development leader"]),
    dict(key="exec_office", label="Exec Office / EA / Admin", products=["Plum"], role="influencer", seats=2.8,
         variants=["executive assistant", "chief of staff", "office manager",
                   "executive office", "administrative manager"]),
]

# ---------------------------------------------------------------------- BREADTH
# Share of companies at 200+ employees that have this role AT ALL. This is what gates
# TAM, not the product's industry fit: every large company has a CFO, but only airlines
# have an FFP manager and only BFSI has a Head of Cards. Sizing niche vertical titles
# off a product-level fit overstates them by an order of magnitude.
BREADTH = {
    # Empuls -- horizontal HR, gated mostly by whether the company is big enough to
    # have specialised the role out of a generalist HR team.
    "chro": 0.55, "vp_hr": 0.50, "hr_director": 0.80, "hr_manager": 0.92,
    "hrbp": 0.60, "hr_ops": 0.70, "total_rewards": 0.22, "comp_ben": 0.40,
    "employee_experience": 0.18, "engagement": 0.20, "internal_comms": 0.30,
    "wellbeing": 0.15, "people_analytics": 0.14, "people_culture": 0.25,
    "payroll": 0.55, "learning": 0.45, "cfo": 0.90, "finance_ops": 0.70,
    "coo_ops": 0.75, "procurement": 0.65, "it_lead": 0.85, "sales_comp": 0.55,
    # Loyalife -- vertical-gated. Loyalty roles only exist where there is a consumer
    # base and a live programme: BFSI, retail, telco, airlines, hospitality, auto, fuel.
    "cmo": 0.55, "cco_commercial": 0.20, "cdo_digital": 0.25, "loyalty_head": 0.10,
    "loyalty_ops": 0.10, "crm_head": 0.30, "growth_head": 0.25, "retention": 0.12,
    "lifecycle": 0.18, "rewards_prog": 0.08, "cards_banking": 0.04, "membership": 0.06,
    "cvm_customer": 0.12, "partnerships": 0.30, "channel": 0.22, "trade_marketing": 0.10,
    "retail_media": 0.04, "regional_sales": 0.30, "ffp_airline": 0.004,
    "aftermarket_auto": 0.02, "specification": 0.01, "patient_exp": 0.04,
    "liveops_gaming": 0.015,
    # Plum -- broad commercial + ops, with a few vertical-only tails.
    "vp_marketing": 0.70, "demand_gen": 0.35, "events": 0.25, "customer_success": 0.35,
    "promotions": 0.15, "research_insights": 0.18, "community": 0.12,
    "product_payments": 0.35, "program_mgmt": 0.60, "claims_insurance": 0.04,
    "clinical_trials": 0.03, "legal_ops": 0.20, "resident_exp": 0.02,
    "sdr_leadership": 0.20, "exec_office": 0.80,
}

# ------------------------------------------------------------------ FINDABILITY
# How well B2B data vendors index this title, relative to a standardised C-suite title.
# Two things drive it: whether the title string is standardised across companies, and
# whether holders keep a public professional profile. "CFO" is both; "Settlement
# Administrator" is neither. This is the per-title variance that a flat regional
# coverage rate hides, and it is what apollo_title_counts.py measures directly.
FINDABILITY = {
    # standardised C-suite: near-perfect indexing
    "chro": 1.00, "cfo": 1.00, "cmo": 1.00, "coo_ops": 0.95, "it_lead": 0.95,
    "cco_commercial": 0.90, "cdo_digital": 0.85, "product_payments": 0.85,
    # standard senior functional titles
    "vp_hr": 0.92, "hr_director": 0.92, "vp_marketing": 0.92, "hr_manager": 0.90,
    "sales_comp": 0.88, "customer_success": 0.85, "growth_head": 0.85,
    "crm_head": 0.85, "finance_ops": 0.80, "procurement": 0.80, "payroll": 0.80,
    "hrbp": 0.85, "hr_ops": 0.80, "comp_ben": 0.80, "learning": 0.80,
    "program_mgmt": 0.78, "demand_gen": 0.78, "regional_sales": 0.78,
    "partnerships": 0.78, "exec_office": 0.75, "total_rewards": 0.75,
    "events": 0.72, "lifecycle": 0.72, "loyalty_head": 0.72, "sdr_leadership": 0.70,
    "channel": 0.70, "research_insights": 0.70, "loyalty_ops": 0.68,
    "people_culture": 0.68, "internal_comms": 0.68, "trade_marketing": 0.65,
    "community": 0.65, "cards_banking": 0.62, "retention": 0.62,
    # niche or emergent titles: inconsistent strings, thinner indexing
    "engagement": 0.58, "employee_experience": 0.58, "people_analytics": 0.55,
    "wellbeing": 0.55, "cvm_customer": 0.55, "promotions": 0.55,
    "rewards_prog": 0.55, "membership": 0.52, "claims_insurance": 0.52,
    "patient_exp": 0.50, "liveops_gaming": 0.50, "aftermarket_auto": 0.48,
    "legal_ops": 0.45, "retail_media": 0.45, "clinical_trials": 0.45,
    "ffp_airline": 0.40, "specification": 0.38, "resident_exp": 0.35,
}

for _f in FAMILIES:
    _f["breadth"] = BREADTH[_f["key"]]
    _f["findability"] = FINDABILITY[_f["key"]]

BY_KEY = {f["key"]: f for f in FAMILIES}


def for_product(product):
    return [f for f in FAMILIES if product in f["products"]]


def seats_at(family, band):
    return family["seats"] * SIZE_MULT[band]

