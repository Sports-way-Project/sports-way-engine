from app.services import llm_client

# ── Website chatbot — public, customer-facing, restricted scope ──────────
WEBSITE_SYSTEM_PROMPT = """You are Ace, the public Sports Way Trading storefront assistant.
You may answer: product stock, pricing, store location, opening hours, delivery
options, return policy, and basic product info (size/color/specs).
You must NOT discuss: internal costs/margins, supplier details, other customers'
data, or anything outside a customer's own shopping question.
If asked something outside this scope, do not guess — say you'll connect them
to the team on WhatsApp, and hand off with context (what product/page they were
on and what they asked)."""

WEBSITE_RULES: list[tuple[tuple[str, ...], str]] = [
    (("in stock", "stock", "available"),
     "Let me check that for you — once this is wired to live Dolibarr stock, I'll give you the exact quantity in real time. For this demo: yes, it's in stock."),
    (("price", "cost", "how much"),
     "Once connected live, I'll pull this straight from Dolibarr's pricing. For this demo: this item is 300 QAR."),
    (("where are you", "location", "address"),
     "Sports Way Trading is based in Doha, Qatar."),
    (("hour", "open", "when are you open"),
     "Our team is available Saturday-Thursday, 9am-6pm."),
    (("deliver", "shipping", "delivery"),
     "Yes, we deliver across Qatar — usually within 2-3 business days, with free shipping on orders over 300 QAR."),
    (("return", "refund", "exchange"),
     "You can return unused items in original packaging within 7 days of delivery for a full refund or exchange."),
    (("size", "color", "colour", "spec", "material", "dimensions"),
     "Once connected live, I'll pull the exact specs for this product from its Dolibarr/catalog listing. For now this is demo data."),
]

WEBSITE_DEFAULT_REPLY = "That's a bit outside what I can help with directly — let me connect you to our team on WhatsApp with your question and which product you were looking at, so they can pick up right where we left off."


# ── Dolibarr copilot — internal, staff-only, fuller access ────────────────
INTERNAL_SYSTEM_PROMPT = """You are the internal Sports Way Trading sales copilot,
used by staff inside Dolibarr. You have fuller access: stock levels across the
catalog, customer order history, quotes, and revenue reporting. You can also
trigger actions (e.g. drafting a quote) but every data-changing action must be
confirmed by the staff member before being applied. Never expose customer data
outside this authenticated, internal context."""

INTERNAL_RULES: list[tuple[tuple[str, ...], str]] = [
    (("low stock", "low on stock", "running low"),
     "Checking live Dolibarr stock next — for this demo: 6 products are below their reorder threshold, including Adjustable Dumbbell Set (3 left) and Academy Team Backpack (5 left)."),
    (("haven't ordered", "inactive customer", "3 months", "not ordered"),
     "For this demo: 14 customers haven't placed an order in the last 3 months. I can draft a re-engagement email list once this is wired to live customer data."),
    (("pending quote", "quotes pending", "open quote"),
     "For this demo: 8 quotes are still pending customer confirmation, 3 of which are older than 2 weeks."),
    (("revenue", "sales this week", "sales this month", "total sales"),
     "For this demo: revenue this week is 42,300 QAR, and 168,500 QAR month-to-date."),
    (("create a quote", "draft a quote", "new quote"),
     "I can draft that — tell me the customer and the products/quantities, and I'll prepare the quote in Dolibarr for your review before it's created. (Prototype: actual creation wiring comes next.)"),
    (("order history", "customer history", "summarize this customer"),
     "For this demo: this customer has placed 7 orders over 14 months, totalling 5,200 QAR, most recently a gym flooring order 3 weeks ago."),
    (("top selling", "best seller", "sold the most"),
     "For this demo, this month's top sellers are: Adjustable Dumbbell Set, Academy Team Backpack, and Commercial Treadmill Pro X9."),
    (("weekly report", "sales report", "generate a report"),
     "For this demo, here's a sample weekly report: revenue 42,300 QAR, 37 orders, 6 low-stock products, top seller Adjustable Dumbbell Set. Once live, I'll generate this straight from Dolibarr on a schedule."),
]

INTERNAL_DEFAULT_REPLY = "I can help with stock levels, customer order history, quotes, and sales reporting internally. Try asking about low stock, pending quotes, or this week's revenue."


async def get_website_reply(message: str) -> str:
    return await llm_client.generate_reply(message, WEBSITE_SYSTEM_PROMPT, WEBSITE_RULES, WEBSITE_DEFAULT_REPLY)


async def get_internal_reply(message: str) -> str:
    return await llm_client.generate_reply(message, INTERNAL_SYSTEM_PROMPT, INTERNAL_RULES, INTERNAL_DEFAULT_REPLY)
