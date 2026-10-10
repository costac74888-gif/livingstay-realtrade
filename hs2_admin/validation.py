from datetime import date
from hs2_design.domain import ContractError
from hs2_listings.validation import identifier
from hs2_help.content import content
from hs2_finance.policy import ReviewedPolicy

KINDS={"faq","policy","promotion","report","review"}


def admin(value):
    if type(value) is not int or value<=0:raise ContractError("ADMIN_REQUIRED")
    return value


def text(value,limit=2000):
    if type(value) is not str or not 1<=len(value.strip())<=limit or "\0" in value:raise ContractError("ADMIN_TEXT_REQUIRED")
    return value.strip()


def payload(kind,raw):
    if kind not in KINDS or type(raw) is not dict:raise ContractError("INVALID_ADMIN_KIND")
    data=raw.copy()
    if kind=="faq":
        if set(data)!={"faq_id","question","answer"} or data["faq_id"] not in {f["id"] for f in content()["faqs"]}:raise ContractError("KNOWN_FAQ_REQUIRED")
        data["question"]=text(data["question"],180);data["answer"]=text(data["answer"],3000)
    elif kind=="policy":
        if set(data)!={"title","note","deposit_krw","pg_processing_krw","platform_bps","deposit_return_days","settlement_days"}:raise ContractError("EXPLICIT_POLICY_REQUIRED")
        data["title"]=text(data["title"],120);data["note"]=text(data["note"])
        if type(data["platform_bps"]) is not int or data["platform_bps"]!=0:raise ContractError("INITIAL_PLATFORM_ZERO_REQUIRED")
        from hs2_finance.policy import money
        money(data["deposit_krw"])
        ReviewedPolicy("validation",**{k:v for k,v in data.items() if k not in {"title","note"}},reviewed=True).terms(max(1,10**11-data["deposit_krw"]))
    elif kind=="promotion":
        if set(data)!={"application_id","title","start","end","amount_krw","note"}:raise ContractError("EXPLICIT_PROMOTION_REQUIRED")
        identifier(data["application_id"]);data["title"]=text(data["title"],120);data["note"]=text(data["note"])
        from hs2_finance.policy import money
        money(data["amount_krw"])
        try:start,end=date.fromisoformat(data["start"]),date.fromisoformat(data["end"])
        except (ValueError,TypeError):raise ContractError("INVALID_PROMOTION_DATES")
        if not 0<(end-start).days<=366:raise ContractError("INVALID_PROMOTION_DATES")
    else:
        if set(data)!={"application_id","title","note"}:raise ContractError("EXPLICIT_CASE_REQUIRED")
        identifier(data["application_id"]);data["title"]=text(data["title"],120);data["note"]=text(data["note"])
    return data
