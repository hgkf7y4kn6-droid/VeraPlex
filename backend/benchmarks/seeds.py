"""Hand-authored seed content for the synthetic benchmark. Every SOP below is invented for this benchmark;
none is copied from a real company or regulator. Numeric parameters are arbitrary on purpose."""

# id, title, paragraphs, [(query, gold_fact_substring)], deviation seed text for the grounding task
SOPS = [
    ("SOP-CLN-001", "Line clearance before batch start", [
        "Before each batch starts, the operator performs line clearance of the filling line. All labels, cartons, packaging components and product residues from the previous batch are removed from the line and from the adjacent staging area.",
        "A second person independently verifies that the area is empty and signs the line clearance checklist. The line must not be released for filling until the verifier's signature is recorded and the supervisor has countersigned.",
        "If any component from a previous batch is found after release, filling stops immediately, the batch is placed on hold and a deviation is raised within the same shift.",
    ], [("who double-checks that the packaging area is empty before we begin a new lot", "second person independently verifies"),
        ("what to do if leftover cartons from the last lot turn up after the line was released", "filling stops immediately")],
     ("Leftover cartons from previous lot found on filling line after release", "FL-12", "Cartons labelled with the previous product were found on the infeed conveyor 20 minutes after line release.")),
    ("SOP-CAL-014", "Calibration of balances and pressure gauges", [
        "Analytical balances are calibrated daily with two certified check weights; production balances weekly. Pressure gauges on process equipment are calibrated every six months against a traceable reference standard.",
        "The acceptance limit for gauge calibration is plus or minus 1.0 percent of span. An instrument found outside tolerance is tagged out of service immediately.",
        "When an instrument is found out of tolerance, an impact assessment covers all batches processed since the last successful calibration, and quality assurance decides on batch disposition.",
    ], [("how far can a pressure gauge read from the reference before it fails calibration", "plus or minus 1.0 percent"),
        ("which batches need reviewing after an instrument fails its check", "since the last successful calibration")],
     ("Pressure gauge on reactor found out of tolerance at calibration", "RX-04", "The six-monthly calibration showed the gauge reading 1.8 percent of span high against the reference standard.")),
    ("SOP-ENV-007", "Environmental monitoring of cleanrooms", [
        "Viable air sampling is performed in grade A zones during every filling session and in grade B rooms weekly. Settle plates are exposed for up to four hours; contact plates are taken from personnel gloves at exit from grade A.",
        "Alert level for grade B settle plates is 5 CFU per plate and the action limit is 10 CFU per plate. Any grade A growth is an action-level event regardless of count.",
        "An action-level excursion requires identification of the isolate to species, a review of the preceding 30 days of trend data and an assessment of product impact before the room is released.",
    ], [("what colony count on a grade B settle plate forces us to act", "10 CFU per plate"),
        ("do we have to identify what grew when a limit is exceeded in the cleanroom", "identification of the isolate to species")],
     ("Growth detected on grade A settle plate during filling", "FL-12", "One colony was recovered on a settle plate positioned at the stopper bowl during a filling session.")),
    ("SOP-CLD-003", "Cold chain storage and temperature excursions", [
        "Refrigerated materials are stored between 2 and 8 degrees Celsius in qualified units monitored by a continuous data logger with alarm. Logger data is reviewed each working day.",
        "A temperature excursion outside the storage range must be reported to quality assurance immediately. Affected product is quarantined and labelled on hold until assessed.",
        "Stability data supplied by the manufacturer is used to assess excursions. An excursion of less than 12 hours that never exceeds 15 degrees Celsius may be assessed for use; longer or warmer excursions require rejection unless supported by additional data.",
    ], [("what is the permitted temperature range for the refrigerators holding raw materials", "between 2 and 8 degrees Celsius"),
        ("can product be used after a short warm spell in cold storage", "less than 12 hours")],
     ("Refrigerator alarm: temperature reached 11 degrees overnight", "RF-02", "The data logger recorded 11 degrees Celsius for about 7 hours; the alarm was acknowledged the next morning.")),
    ("SOP-CLE-022", "Cleaning and sanitisation of filling equipment", [
        "Product contact parts of the filler, including seals, gaskets, tubing and needles, are cleaned and sanitised after each campaign using the validated detergent and a 70 percent isopropanol rinse.",
        "Gaskets and seals are visually inspected at every cleaning. Any worn, cracked or weeping seal is replaced immediately and the replacement is recorded in the equipment logbook.",
        "Cleaning effectiveness is verified by swab sampling of defined locations; the residue limit is 10 parts per million of the previous product. Equipment may not be used until swab results are approved.",
    ], [("seal on the filler is weeping what is the rule for worn gaskets", "replaced immediately"),
        ("residue limit after cleaning of product contact parts", "10 parts per million")],
     ("Product leaking from filler seal during run", "FL-12", "A weeping gasket on the filling pump was noticed mid-run; about 40 vials were affected.")),
    ("SOP-GWN-005", "Personnel gowning and qualification", [
        "Operators entering grade B and grade A areas complete gowning qualification before first entry and requalify every twelve months. Qualification includes three consecutive acceptable finger-dab plates.",
        "Gowning follows the defined sequence: hand wash, hood, mask, coverall, boots and sterile gloves. Gloves are sanitised every 30 minutes in grade A.",
        "Visible damage to gowning, such as a tear or loose hood, requires the person to leave the area, regown and report the event to the supervisor.",
    ], [("how often must cleanroom staff requalify for gowning", "every twelve months"),
        ("what should an operator do about a torn coverall in the clean area", "leave the area, regown")],
     ("Operator entered grade B with torn glove cuff", "CR-B1", "A supervisor noticed a split in the sterile glove cuff of an operator already working inside the grade B room.")),
    ("SOP-SMP-011", "Sampling of incoming raw materials", [
        "Each delivered container is checked for intact seals and correct labelling before sampling. Sampling takes place in the sampling booth under laminar airflow using clean, dedicated tools.",
        "The number of containers sampled is the square root of the number received, plus one, rounded up. Identity testing is performed on every container of an active ingredient.",
        "Samples are labelled with material code, lot, date and sampler's initials. Sampled containers receive a green sampled sticker and are returned to quarantine until released.",
    ], [("how many drums from a delivery do we have to sample", "square root of the number received"),
        ("must every container of an active substance be identity tested", "every container of an active ingredient")],
     ("Sampling performed without identity test on all active ingredient drums", "SB-01", "Review of a delivery of 9 drums showed identity testing recorded for only three of them.")),
    ("SOP-WTR-009", "Purified water system monitoring", [
        "Purified water is monitored continuously for conductivity and daily at point of use for total organic carbon. The conductivity alert limit is 1.0 microsiemens per centimetre at 25 degrees Celsius.",
        "Microbial counts are tested weekly at all loops; the action limit is 100 CFU per millilitre and the alert level is 50 CFU per millilitre.",
        "On an action-level result the affected outlet is taken out of use, resanitised with hot water at 80 degrees Celsius for one hour, and retested before release.",
    ], [("what total viable count in the purified water loop requires action", "100 CFU per millilitre"),
        ("how is an outlet recovered after a failed microbial test", "hot water at 80 degrees")],
     ("Purified water conductivity alarm at point of use", "PW-LOOP", "Conductivity at point of use rose to 1.4 microsiemens per centimetre for two hours.")),
    ("SOP-HVC-012", "HVAC differential pressure control", [
        "Differential pressure between adjacent rooms of different classification is recorded continuously. Higher classification rooms are maintained at positive pressure of at least 10 pascals relative to the adjacent lower classification room.",
        "An alarm sounds if the differential falls below 10 pascals for more than two minutes. Operators stop open processing and secure open product when the alarm sounds.",
        "Filter integrity of terminal HEPA filters is tested every six months by particle challenge; filters failing the test are replaced before the room returns to use.",
    ], [("minimum pressure difference between the cleanroom and the corridor", "at least 10 pascals"),
        ("how often are the final HEPA filters tested", "every six months by particle challenge")],
     ("Differential pressure alarm between grade B room and corridor", "CR-B1", "The differential dropped to 6 pascals for about ten minutes while a door was held open during equipment transfer.")),
    ("SOP-LBL-018", "Label issue and reconciliation", [
        "Printed labels are issued against the batch record by a controlled issuing clerk. Each issue is counted and signed, and unused labels are returned the same shift.",
        "At the end of packaging, labels issued, used, destroyed and returned must reconcile exactly. Any discrepancy, however small, must be investigated before the batch can be released.",
        "Rejected or obsolete labels are destroyed under witness and the destruction is recorded with quantities.",
    ], [("do label counts have to match exactly at the end of packaging", "must reconcile exactly"),
        ("who hands out printed labels for a batch", "controlled issuing clerk")],
     ("Label reconciliation shows two labels unaccounted for", "PK-03", "Issued 12,000 labels, used 11,640, destroyed 358, returned 0; two labels are unaccounted for.")),
    ("SOP-STR-020", "Steam sterilisation cycles", [
        "Autoclave loads are sterilised at 121 degrees Celsius for a minimum of 15 minutes at the load probe, with the load pattern defined in the validated loading diagram.",
        "Biological indicators containing Geobacillus stearothermophilus are placed at the cold spot in each qualification run. Chemical indicator tape is applied to every item.",
        "Cycle recorder printouts are reviewed and signed by a second person. Any cycle that does not reach the set temperature at the load probe for the full time is rejected and the load re-processed once.",
    ], [("what temperature and time must the autoclave load reach", "121 degrees Celsius for a minimum of 15 minutes"),
        ("what happens to a cycle that fails to hold temperature for the full period", "rejected and the load re-processed once")],
     ("Autoclave cycle aborted with low temperature at load probe", "AC-02", "The load probe reached only 117 degrees for 9 minutes before the cycle aborted on a steam supply fault.")),
    ("SOP-FLT-016", "Sterilising filter integrity testing", [
        "Sterilising grade filters are integrity tested before and after use. The post-use test confirms the filter was intact during filtration.",
        "Bubble point or pressure hold tests are performed using the filter manufacturer's validated specification. A bubble point below specification is a failure.",
        "A failed post-use integrity test requires the filtered bulk to be held. The filter may be rewetted and retested once; a second failure results in rejection of the filtrate unless a documented refiltration is approved.",
    ], [("what do we do if the filter fails its integrity check after filtration", "bulk to be held"),
        ("how many times can a failed filter be retested", "retested once")],
     ("Post-use filter integrity test failed on bulk solution", "FT-01", "The post-use bubble point was 2.6 bar against a specification of at least 3.2 bar.")),
    ("SOP-TAB-024", "In-process control of tablet compression", [
        "During compression, tablet weight is checked every 30 minutes on a sample of 20 tablets. Individual weights must be within plus or minus 5 percent of the target weight.",
        "Hardness and thickness are measured every hour on 10 tablets. Friability is tested at start-up and after every press speed change, with a limit of 1.0 percent weight loss.",
        "If weight, hardness or friability results fall outside limits, the press is stopped, tablets since the last good check are segregated and the cause is investigated before restart.",
    ], [("allowed variation of individual tablet weight during compression", "plus or minus 5 percent of the target weight"),
        ("what happens to tablets made since the last passing check when a limit is exceeded", "segregated")],
     ("Tablet friability result above limit at press speed change", "TP-05", "Friability measured 1.6 percent loss after the press speed was increased.")),
    ("SOP-OOS-030", "Handling of out-of-specification laboratory results", [
        "Any result outside specification is reported to the laboratory supervisor immediately. The analyst must not retest or discard solutions before the supervisor authorises a phase one laboratory investigation.",
        "Phase one checks for assignable laboratory error such as calculation mistakes, instrument faults or sample preparation errors. If an assignable cause is documented, the result is invalidated and the test repeated.",
        "If no laboratory error is found, a phase two full-scale investigation involving manufacturing review is opened. Averaging results to obtain a passing value is prohibited.",
    ], [("can an analyst simply retest straight away after a failing result", "must not retest"),
        ("is it acceptable to average a failing and passing result", "Averaging results"),],
     ("Assay result below specification on stability sample", "HPLC-3", "The 6-month stability assay gave 93.1 percent label claim against a limit of 95.0 to 105.0 percent.")),
    ("SOP-CMP-033", "Product complaint handling", [
        "All product complaints are logged within one working day of receipt with product name, batch number, complainant details and a description of the defect.",
        "Complaints suggesting a potential quality defect with risk to patients are escalated to quality assurance the same day. A written acknowledgement is sent to the complainant within five working days.",
        "Retained samples of the complained batch are examined and the batch record reviewed. The investigation outcome and trend of similar complaints are reviewed quarterly.",
    ], [("how quickly must a customer complaint be recorded", "within one working day"),
        ("how soon is the complainant sent a written acknowledgement", "within five working days")],
     ("Complaint of particulate matter in vial from distributor", "FL-12", "A hospital pharmacy reported visible particles in two vials of one batch.")),
    ("SOP-DOC-002", "Good documentation practice", [
        "Entries in controlled records are made in indelible ink at the time the activity is performed. Pencil, correction fluid and overwriting are not permitted.",
        "A correction is made by drawing a single line through the original entry so it remains legible, then writing the correct value with the date, initials and a reason for the change.",
        "Blank spaces on a record are lined through and initialled. Transcribing data from loose notes onto the record afterwards is not permitted.",
    ], [("how should a wrong entry in a batch record be corrected", "single line through the original entry"),
        ("is it allowed to copy readings from scrap paper into the record later", "Transcribing data from loose notes")],
     ("Batch record entry corrected with correction fluid", "PK-03", "A packaging record was found with a reading covered by correction fluid and rewritten.")),
]

# queries with no relevant SOP in the corpus (retrieval should abstain)
UNANSWERABLE_QUERIES = [
    "unblinding procedure for a clinical trial randomisation code break",
    "aggregation and serialisation of cases under supply chain track and trace rules",
    "radiation shielding requirements for handling radioactive isotopes",
    "husbandry and welfare checks in the animal facility",
    "intake of adverse drug reaction reports from healthcare professionals",
    "refilling cryogenic liquid nitrogen dewars safely",
    "export licensing for controlled narcotic substances",
    "quarterly cafeteria menu and staff canteen opening hours",
]

# Deviations that the SOP corpus and prior events cannot explain (grounding: must abstain)
UNANSWERABLE_DEVIATIONS = [
    ("Unusual odour reported in the warehouse office", "WH-OFF", "Two staff reported a chemical-like smell in the warehouse office in the morning; it was gone by noon."),
    ("Pallet jack collided with racking in bay 4", "WH-04", "A pallet jack struck a rack upright; no pallets fell and no product was damaged."),
    ("Visitor badge not returned after site audit", "SEC-01", "A visitor badge issued for an external audit was not handed back at reception."),
    ("Printer in the QA office produced blank pages for a controlled form", "QA-PR1", "A controlled form template printed with blank pages and was reprinted."),
    ("Forklift battery charger tripped the breaker", "WH-CH2", "The breaker feeding the forklift charging bay tripped twice in one hour."),
    ("Fire door in corridor C found wedged open", "BLD-C", "A security walk-round found the corridor C fire door wedged open with a bin."),
    ("Waste bin in changing room not emptied on schedule", "CR-CH", "The changing room waste bin was found full at the start of the shift."),
    ("Pest control trap number 14 missing from route", "PC-14", "The pest control contractor reported trap 14 absent from its mounting."),
]

EVENT_TYPES = ["temperature_excursion", "equipment_failure", "contamination", "documentation_error", "process_deviation", "labeling_error"]
AREAS = ["Filling Suite 2", "Cold Store A", "Packaging Hall 3", "Granulation Room", "QC Laboratory", "Warehouse Bay 4", "Cleanroom B1", "Compression Suite"]
