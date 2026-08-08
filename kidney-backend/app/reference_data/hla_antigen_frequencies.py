# app/reference_data/hla_antigen_frequencies.py
"""
Frozen population HLA antigen frequency table for cPRA, replacing the old
approach of deriving frequencies from this system's own live database
(app/services/hla_typing_service.py's now-removed get_population_hla_profiles).
That approach made a patient's cPRA drift as unrelated data got entered, was
computed from a biased pool (patients + their own blood-relative living
donors), and had a denominator bug on top. See cpra_service.py for the
combination math that consumes this table.

Source: Grifoni A, Weiskopf D, Lindestam Arlehamn CS, et al. "Sequence-based
HLA-A, B, C, DP, DQ, and DR typing of 714 adults from Colombo, Sri Lanka."
Hum Immunol. 2018;79(2):87-88. doi:10.1016/j.humimm.2017.12.007.
PMID:29289740. Confirmed via the paper's own abstract to be the source
behind Allele Frequencies Net Database's "Sri Lanka Colombo" population
entry (AFND population ID 3423) -- 714 healthy adult blood bank donors from
all 26 districts, typed at all 7 loci, no Hardy-Weinberg deviations at any
locus.

Methodology: rather than transcribing the paper's own summarized frequency
table (real transcription risk for ~100 numbers by hand), these values were
computed by direct counting from AFND's raw ambiguity-resolved genotype
export for population 3423
(http://www.allelefrequencies.net/tools/getrawdata.asp?pop_id=3423&resolved=true,
one row per donor, both alleles at all 7 loci, fetched 2026-08-08) --
verified as exactly 714 well-formed rows, all 7 loci present on every row.
Each molecular allele (e.g. "A*33:03") was collapsed to this codebase's
existing serological antigen designation using the *same* convention
hla_typing_service.hla_antigen_designation() already applies to this
system's own patient/donor typing data: locus + the allele's first field,
zero-stripped (so "A*33:03" -> "A33", "DRB1*07:01" -> "DR7"). A person
"carries" an antigen if either chromosome has it; frequency is the fraction
of the 714 donors carrying it (phenotype/carrier frequency, not raw allele
frequency) -- this matches the carrier-frequency semantics the old
(buggy) calculate_population_antigen_frequencies already used, and is the
correct quantity for cPRA's union-probability combination in
cpra_service.py. Sanity-checked against the paper's own reported highlights
(e.g. A*33:03/A*24:02 as class I alleles ">30%") -- consistent once you
account for allele-vs-phenotype frequency (phenotype freq ~= 2p-p^2).

DQA1 was typed by this study (714/714) but is deliberately excluded here:
_SEROLOGICAL_LOCUS_PREFIX in hla_typing_service.py has no entry for it, so
hla_antigen_designation() never produces a DQA1-style key from real
antibody bead-specificity chart data -- there is no vocabulary overlap to
serve. DPA1 and the composite DRB3,4,5 locus are excluded for the same
reason and also weren't typed by this study. That leaves the 97 antigens
below, across the 6 loci (A, B, C, DPB1, DQB1, DRB1) that
sensitized_antigens can actually contain.

Known limitation -- linkage disequilibrium: cpra_service.py combines these
single-locus frequencies as if sensitization to each antigen were an
independent event. HLA loci are not independent (haplotypes like
A1-B8-DR3 travel together), so this inflates cPRA for patients sensitized
against antigens on a shared haplotype. This is a disclosed approximation,
not fixed here. The source paper *does* report real per-cohort haplotype
frequencies for this exact population (950 EM-estimated haplotypes across
all 7 loci, Supplementary Table III) which would be the right input for a
real fix -- but that table was not obtainable this pass (PMC gates the
supplementary file behind a JS-driven download flow that blocked both a
fetch and a direct HTTP request; the AllelefrequenciesNet haplotype-page
URL guessed from the site's own link text 404'd, and the site's real
navigation is JS-driven so the correct URL wasn't found). If that table
ever becomes available, this is where a haplotype-aware combination step
should plug in.

Note on precision: several DPB1 entries are single-observation frequencies
(e.g. "DP109": 0.0014 = 1/714) -- DPB1 genuinely has far more distinct
allele groups than A/B/C/DR/DQ in this cohort; verified these are real,
well-formed calls in the raw data, not a parsing artifact. Single-
observation frequencies carry wide sampling uncertainty inherent to a
714-person cohort, not something trimming the table would fix.

Bump HLA_FREQUENCY_TABLE_VERSION any time the values below change (e.g. a
better/larger reference cohort, or a haplotype-aware successor), so
existing stored CPRAResult.reference_table_version values on old reports
keep meaning exactly what they meant when computed.
"""

HLA_FREQUENCY_TABLE_SAMPLE_SIZE = 714

HLA_FREQUENCY_TABLE_VERSION = "grifoni-colombo-2018-v1"

HLA_FREQUENCY_TABLE_CITATION = (
    "Grifoni et al., Hum Immunol. 2018;79(2):87-88, "
    "doi:10.1016/j.humimm.2017.12.007, PMID:29289740 (AFND population 3423)"
)

HLA_ANTIGEN_FREQUENCIES: dict[str, float] = {
    "A24": 0.3641, "A33": 0.3403, "A11": 0.2661, "A2": 0.2563, "A1": 0.2115,
    "A68": 0.1190, "A3": 0.1078, "A26": 0.0686, "A31": 0.0448, "A32": 0.0308,
    "A30": 0.0168, "A23": 0.0140, "A29": 0.0140,
    "B35": 0.2311, "B40": 0.2115, "B15": 0.1821, "B57": 0.1779, "B44": 0.1653,
    "B7": 0.1373, "B58": 0.1345, "B52": 0.1303, "B51": 0.1303, "B55": 0.0868,
    "B37": 0.0728, "B13": 0.0532, "B18": 0.0336, "B8": 0.0294, "B27": 0.0280,
    "B56": 0.0266, "B39": 0.0196, "B49": 0.0126, "B38": 0.0112, "B48": 0.0084,
    "B50": 0.0056, "B53": 0.0042, "B41": 0.0042, "B78": 0.0042, "B14": 0.0028,
    "Cw7": 0.4020, "Cw4": 0.2619, "Cw6": 0.2549, "Cw3": 0.2157, "Cw12": 0.2157,
    "Cw15": 0.1793, "Cw1": 0.1148, "Cw14": 0.0756, "Cw8": 0.0644, "Cw16": 0.0364,
    "Cw2": 0.0112, "Cw5": 0.0098, "Cw17": 0.0028,
    "DP4": 0.5644, "DP2": 0.4202, "DP13": 0.1597, "DP26": 0.1401, "DP9": 0.1022,
    "DP3": 0.0966, "DP14": 0.0938, "DP1": 0.0686, "DP17": 0.0266, "DP15": 0.0252,
    "DP16": 0.0196, "DP10": 0.0182, "DP5": 0.0112, "DP28": 0.0112, "DP21": 0.0084,
    "DP83": 0.0042, "DP20": 0.0028, "DP45": 0.0014, "DP109": 0.0014, "DP526": 0.0014,
    "DP117": 0.0014, "DP19": 0.0014, "DP6": 0.0014, "DP57": 0.0014, "DP81": 0.0014,
    "DP51": 0.0014, "DP25": 0.0014, "DP73": 0.0014,
    "DQ3": 0.5294, "DQ6": 0.4902, "DQ5": 0.4510, "DQ2": 0.2801, "DQ4": 0.0196,
    "DR15": 0.3824, "DR7": 0.3796, "DR14": 0.2255, "DR13": 0.1793, "DR4": 0.1709,
    "DR10": 0.1204, "DR11": 0.0798, "DR3": 0.0784, "DR1": 0.0700, "DR12": 0.0686,
    "DR8": 0.0378, "DR9": 0.0238, "DR16": 0.0196,
}
