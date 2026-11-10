"""What the app pulls out of each loan document, and the checks it runs across a loan file."""

from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    TERM_SHEET = "term_sheet"
    APPRAISAL = "appraisal"
    REHAB_BUDGET = "rehab_budget"
    DRAW_REQUEST = "draw_request"
    OTHER = "other"


class LoanDocumentFields(BaseModel):
    """The fields Claude extracts from one document. Null when the document doesn't state it."""

    doc_type: DocType
    borrower_name: str | None = Field(description="The borrowing entity, e.g. an LLC, not the guarantor")
    property_address: str | None = Field(description="Full street address of the subject property")
    purchase_price: int | None = Field(description="Contract or purchase price in whole dollars")
    loan_amount: int | None = Field(description="Total loan amount in whole dollars")
    interest_rate_pct: float | None = Field(description="Note rate as a percent, e.g. 11.5")
    term_months: int | None = Field(description="Loan term in months")
    origination_points: float | None = Field(description="Origination fee in points")
    as_is_value: int | None = Field(description="Appraised market value as is, in whole dollars")
    after_repair_value: int | None = Field(
        description="Appraised value after the renovation (ARV, or prospective value upon completion)"
    )
    rehab_budget_total: int | None = Field(description="Total rehab or renovation budget in whole dollars")
    draw_number: int | None = Field(description="Draw request number")
    draw_amount_requested: int | None = Field(
        description="Amount requested in this draw only, not amounts previously disbursed"
    )


FIELD_NAMES = [name for name in LoanDocumentFields.model_fields if name != "doc_type"]


class Flag(BaseModel):
    code: str
    severity: str  # "warning" or "info"
    message: str


# Lending guidelines the checks apply. A real lender would set these per loan program.
MAX_ARV_LTV_PCT = 70.0
MAX_LTC_PCT = 90.0


def loan_file_flags(docs: list[LoanDocumentFields]) -> list[Flag]:
    """Deterministic checks across a loan file's extracted fields. No model involved."""

    def first(field: str, doc_type: DocType | None = None):
        for d in docs:
            if doc_type is not None and d.doc_type != doc_type:
                continue
            value = getattr(d, field)
            if value is not None:
                return value
        return None

    flags: list[Flag] = []
    present = {d.doc_type for d in docs}
    missing = [t for t in (DocType.TERM_SHEET, DocType.APPRAISAL, DocType.REHAB_BUDGET) if t not in present]
    if missing:
        names = ", ".join(t.value.replace("_", " ") for t in missing)
        flags.append(Flag(code="missing_documents", severity="info", message=f"Missing: {names}."))

    loan = first("loan_amount", DocType.TERM_SHEET) or first("loan_amount")
    arv = first("after_repair_value", DocType.APPRAISAL) or first("after_repair_value")
    budget = first("rehab_budget_total", DocType.REHAB_BUDGET) or first("rehab_budget_total")
    price = first("purchase_price", DocType.TERM_SHEET) or first("purchase_price")

    if loan and arv:
        ltv = loan / arv * 100
        if ltv > MAX_ARV_LTV_PCT:
            flags.append(
                Flag(
                    code="arv_ltv_high",
                    severity="warning",
                    message=f"Loan is {ltv:.1f}% of after-repair value, above the {MAX_ARV_LTV_PCT:.0f}% limit.",
                )
            )
    if loan and price and budget:
        ltc = loan / (price + budget) * 100
        if ltc > MAX_LTC_PCT:
            flags.append(
                Flag(
                    code="ltc_high",
                    severity="warning",
                    message=f"Loan is {ltc:.1f}% of purchase plus rehab, above the {MAX_LTC_PCT:.0f}% limit.",
                )
            )

    draws = {d.draw_number: d.draw_amount_requested for d in docs if d.doc_type == DocType.DRAW_REQUEST}
    drawn = sum(a for a in draws.values() if a)
    if budget and drawn > budget:
        flags.append(
            Flag(
                code="draws_over_budget",
                severity="warning",
                message=f"Draws total ${drawn:,}, ${drawn - budget:,} over the ${budget:,} rehab budget.",
            )
        )

    addresses = {_normalize(d.property_address) for d in docs if d.property_address}
    if len(addresses) > 1:
        flags.append(
            Flag(code="address_mismatch", severity="warning", message="Documents name different property addresses.")
        )
    return flags


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace(",", " ").replace(".", " ").split())
