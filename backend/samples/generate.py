"""Renders the sample loan files: fictional PDFs plus the labels the eval scores against.

Every name, address and number here is made up. The documents say so in their
footer, and the lender is a generic "Sample Lending Co.".

    uv run python samples/generate.py

Writes samples/pdfs/<loan>/<doc>.pdf and samples/labels.json.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
LENDER = "Sample Lending Co."
FOOTER = "SAMPLE DOCUMENT - FICTIONAL DATA - NOT A REAL LOAN"


@dataclass
class Draw:
    number: int
    amount: int
    date: str
    completed: list[tuple[str, int]]


@dataclass
class Loan:
    id: str
    borrower: str
    guarantor: str
    address: str
    purchase_price: int
    as_is_value: int
    arv: int
    loan_amount: int
    rate: float
    term_months: int
    points: float
    budget: list[tuple[str, int]]
    draws: list[Draw] = field(default_factory=list)
    appraiser: str = ""
    comps: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def rehab_total(self) -> int:
        return sum(cost for _, cost in self.budget)


LOANS = [
    Loan(
        id="L1",
        borrower="Ridgeline Home Partners LLC",
        guarantor="Dana Whitlock",
        address="1407 Pecan Hollow Dr, Austin, TX 78745",
        purchase_price=312_000,
        as_is_value=320_000,
        arv=465_000,
        loan_amount=340_000,
        rate=11.5,
        term_months=12,
        points=2.0,
        budget=[
            ("Demolition and haul-off", 6_500),
            ("Roof replacement", 14_000),
            ("Kitchen: cabinets, counters, appliances", 27_500),
            ("Bathrooms (2)", 18_000),
            ("Flooring throughout", 12_500),
            ("Interior paint", 5_500),
            ("Contingency", 4_500),
        ],
        draws=[
            Draw(1, 30_000, "March 4, 2026", [("Demolition and haul-off", 6_500), ("Roof replacement", 14_000), ("Kitchen: cabinets, counters, appliances", 9_500)]),
            Draw(2, 35_000, "April 15, 2026", [("Kitchen: cabinets, counters, appliances", 18_000), ("Bathrooms (2)", 17_000)]),
        ],
        appraiser="Hollis Grant, Certified Residential Appraiser",
        comps=[("1311 Pecan Hollow Dr", 472_000, 1_640), ("1520 Crested Butte Ln", 459_500, 1_590), ("8804 Sagebrush Way", 481_000, 1_710)],
    ),
    Loan(
        id="L2",
        borrower="Bluebonnet Renovations LLC",
        guarantor="Marcus Ibarra",
        address="902 Larkspur Ct, Round Rock, TX 78664",
        purchase_price=248_000,
        as_is_value=255_000,
        arv=389_000,
        loan_amount=255_000,
        rate=10.99,
        term_months=9,
        points=1.5,
        budget=[
            ("HVAC system replacement", 11_000),
            ("Electrical panel upgrade", 6_500),
            ("Kitchen remodel", 19_500),
            ("Primary bathroom remodel", 12_000),
            ("Exterior paint and trim", 8_000),
            ("Landscaping", 5_000),
        ],
        draws=[
            Draw(1, 25_000, "February 10, 2026", [("HVAC system replacement", 11_000), ("Electrical panel upgrade", 6_500), ("Kitchen remodel", 7_500)]),
            Draw(2, 22_000, "March 18, 2026", [("Kitchen remodel", 12_000), ("Primary bathroom remodel", 10_000)]),
            Draw(3, 21_500, "May 2, 2026", [("Primary bathroom remodel", 2_000), ("Exterior paint and trim", 8_000), ("Landscaping", 5_000), ("Change order: foundation repair", 6_500)]),
        ],
        appraiser="Renata Okafor, Certified Residential Appraiser",
        comps=[("915 Larkspur Ct", 395_000, 1_480), ("2107 Thistle Bend", 381_000, 1_430), ("640 Prairie Dawn Dr", 402_500, 1_520)],
    ),
    Loan(
        id="L3",
        borrower="Kestrel Capital Holdings LLC",
        guarantor="Priya Natarajan",
        address="55 Cedar Bend Ln, Pflugerville, TX 78660",
        purchase_price=410_000,
        as_is_value=415_000,
        arv=610_000,
        loan_amount=430_000,
        rate=12.25,
        term_months=12,
        points=2.5,
        budget=[
            ("Foundation repair", 22_000),
            ("Framing and second-story addition", 48_000),
            ("Plumbing rough-in and fixtures", 16_000),
            ("Electrical", 14_000),
            ("Drywall and finishes", 12_500),
            ("Contingency", 7_500),
        ],
        draws=[
            Draw(1, 40_000, "June 9, 2026", [("Foundation repair", 22_000), ("Framing and second-story addition", 18_000)]),
        ],
        appraiser="Hollis Grant, Certified Residential Appraiser",
        comps=[("71 Cedar Bend Ln", 598_000, 2_310), ("1209 Windmill Run", 625_000, 2_400), ("344 Copper Hills Dr", 615_500, 2_350)],
    ),
    Loan(
        id="L4",
        borrower="Mesquite Street Investments LLC",
        guarantor="Tomas Lindqvist",
        address="3318 Willow Run, Georgetown, TX 78626",
        purchase_price=189_000,
        as_is_value=195_000,
        arv=289_000,
        loan_amount=190_000,
        rate=11.0,
        term_months=6,
        points=2.0,
        budget=[
            ("Windows (12)", 9_600),
            ("Flooring", 8_400),
            ("Kitchen refresh", 11_000),
            ("Bathroom refresh", 6_500),
            ("Paint, interior and exterior", 5_500),
        ],
        draws=[
            Draw(1, 18_000, "August 3, 2026", [("Windows (12)", 9_600), ("Flooring", 8_400)]),
            Draw(2, 15_000, "September 14, 2026", [("Kitchen refresh", 11_000), ("Bathroom refresh", 4_000)]),
        ],
        appraiser="Renata Okafor, Certified Residential Appraiser",
        comps=[("3402 Willow Run", 292_000, 1_210), ("117 Juniper Creek Rd", 284_500, 1_180), ("2950 Ranch Gate Trl", 297_000, 1_260)],
    ),
]

styles = getSampleStyleSheet()
H1, H2, BODY, SMALL = styles["Title"], styles["Heading2"], styles["BodyText"], styles["Italic"]


def money(n: int) -> str:
    return f"${n:,.0f}"


def table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    t = Table(rows, colWidths=widths)
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecef")),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(0.75 * inch, 0.5 * inch, FOOTER)
    canvas.drawRightString(7.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build(path: Path, story: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(path), pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.8 * inch, title=path.stem,
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def term_sheet(loan: Loan) -> tuple[list, dict]:
    ltc = loan.loan_amount / (loan.purchase_price + loan.rehab_total) * 100
    story = [
        Paragraph(f"{LENDER}<br/>Bridge Loan Term Sheet", H1),
        Paragraph("Non-binding summary of proposed terms. Subject to underwriting, title and appraisal.", SMALL),
        Spacer(1, 12),
        table(
            [
                ["Term", "Proposed"],
                ["Borrowing entity", loan.borrower],
                ["Personal guarantor", loan.guarantor],
                ["Subject property", loan.address],
                ["Purchase price", money(loan.purchase_price)],
                ["Total loan amount", money(loan.loan_amount)],
                ["Note rate", f"{loan.rate:.2f}% interest-only, paid monthly"],
                ["Term", f"{loan.term_months} months"],
                ["Origination fee", f"{loan.points:.1f} points"],
                ["Rehab holdback", f"{money(loan.rehab_total)}, released in draws after inspection"],
                ["Loan-to-cost", f"{ltc:.1f}% of purchase plus rehab"],
                ["Prepayment", "No prepayment penalty after month 3"],
            ],
            [2.1 * inch, 4.6 * inch],
        ),
        Spacer(1, 14),
        Paragraph("Conditions", H2),
        Paragraph(
            "Lender requires a satisfactory appraisal including an after-repair value, a contractor bid "
            "matching the rehab budget, builder's risk insurance, and an entity good-standing certificate. "
            "Draws are funded within three business days of a passed inspection.",
            BODY,
        ),
    ]
    labels = {
        "doc_type": "term_sheet",
        "borrower_name": loan.borrower,
        "property_address": loan.address,
        "purchase_price": loan.purchase_price,
        "loan_amount": loan.loan_amount,
        "interest_rate_pct": loan.rate,
        "term_months": loan.term_months,
        "origination_points": loan.points,
        "rehab_budget_total": loan.rehab_total,
    }
    return story, labels


def appraisal(loan: Loan) -> tuple[list, dict]:
    story = [
        Paragraph("Residential Appraisal Report (Summary)", H1),
        Paragraph(f"Prepared for {LENDER} by {loan.appraiser}", SMALL),
        Spacer(1, 12),
        table(
            [
                ["Item", "Detail"],
                ["Subject property", loan.address],
                ["Client / intended user", LENDER],
                ["Borrower", loan.borrower],
                ["Contract price", money(loan.purchase_price)],
                ["Property rights appraised", "Fee simple"],
            ],
            [2.1 * inch, 4.6 * inch],
        ),
        Spacer(1, 12),
        Paragraph("Comparable sales", H2),
        Paragraph("Recent renovated sales within one mile, adjusted for size and condition.", BODY),
        table(
            [["Address", "Sale price", "Living area (sq ft)"]]
            + [[a, money(p), f"{s:,}"] for a, p, s in loan.comps],
            [3.0 * inch, 1.8 * inch, 1.9 * inch],
        ),
        PageBreak(),
        Paragraph("Reconciliation and opinion of value", H2),
        Paragraph(
            "The sales comparison approach is given the most weight. Values below are as of the "
            "effective date of inspection.",
            BODY,
        ),
        Spacer(1, 8),
        table(
            [
                ["Value premise", "Opinion of value"],
                ["Market value, as is", money(loan.as_is_value)],
                ["Prospective market value upon completion of the proposed renovation", money(loan.arv)],
            ],
            [4.2 * inch, 2.5 * inch],
        ),
        Spacer(1, 10),
        Paragraph(
            f"The prospective value assumes completion of the scope of work in the borrower's "
            f"rehab budget of {money(loan.rehab_total)} in a good and workmanlike manner.",
            BODY,
        ),
    ]
    labels = {
        "doc_type": "appraisal",
        "borrower_name": loan.borrower,
        "property_address": loan.address,
        "purchase_price": loan.purchase_price,
        "as_is_value": loan.as_is_value,
        "after_repair_value": loan.arv,
        "rehab_budget_total": loan.rehab_total,
    }
    return story, labels


def rehab_budget(loan: Loan) -> tuple[list, dict]:
    story = [
        Paragraph("Scope of Work and Rehab Budget", H1),
        Paragraph(f"Borrower: {loan.borrower}<br/>Property: {loan.address}", BODY),
        Spacer(1, 12),
        table(
            [["#", "Line item", "Budget"]]
            + [[str(i + 1), item, money(cost)] for i, (item, cost) in enumerate(loan.budget)]
            + [["", "Total rehab budget", money(loan.rehab_total)]],
            [0.4 * inch, 4.4 * inch, 1.9 * inch],
        ),
        Spacer(1, 12),
        Paragraph(
            "Contractor bids are attached for each line over $10,000. Change orders require lender "
            "approval before work begins.",
            BODY,
        ),
    ]
    labels = {
        "doc_type": "rehab_budget",
        "borrower_name": loan.borrower,
        "property_address": loan.address,
        "rehab_budget_total": loan.rehab_total,
    }
    return story, labels


def draw_request(loan: Loan, draw: Draw) -> tuple[list, dict]:
    prior = sum(d.amount for d in loan.draws if d.number < draw.number)
    story = [
        Paragraph(f"Construction Draw Request No. {draw.number}", H1),
        table(
            [
                ["Field", "Value"],
                ["Borrower", loan.borrower],
                ["Property", loan.address],
                ["Request date", draw.date],
                ["Total rehab budget", money(loan.rehab_total)],
                ["Previously disbursed", money(prior)],
                ["Amount requested this draw", money(draw.amount)],
            ],
            [2.4 * inch, 4.3 * inch],
        ),
        Spacer(1, 12),
        Paragraph("Work completed for this draw", H2),
        table(
            [["Line item", "Amount"]] + [[item, money(cost)] for item, cost in draw.completed],
            [4.8 * inch, 1.9 * inch],
        ),
        Spacer(1, 10),
        Paragraph(
            "Borrower certifies the work above is complete and requests inspection. Lien waivers "
            "from the general contractor are attached.",
            BODY,
        ),
    ]
    labels = {
        "doc_type": "draw_request",
        "borrower_name": loan.borrower,
        "property_address": loan.address,
        "rehab_budget_total": loan.rehab_total,
        "draw_number": draw.number,
        "draw_amount_requested": draw.amount,
    }
    return story, labels


def main() -> None:
    labels: dict[str, dict] = {}
    for loan in LOANS:
        docs = [("term_sheet", term_sheet(loan)), ("appraisal", appraisal(loan)), ("rehab_budget", rehab_budget(loan))]
        docs += [(f"draw_request_{d.number}", draw_request(loan, d)) for d in loan.draws]
        for name, (story, label) in docs:
            rel = f"{loan.id}/{name}.pdf"
            build(HERE / "pdfs" / rel, story)
            labels[rel] = {"loan": loan.id, **label}
    (HERE / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    print(f"Wrote {len(labels)} documents")


if __name__ == "__main__":
    main()
