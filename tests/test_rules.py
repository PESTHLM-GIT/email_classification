from src import rules
from src.config import CATEGORY_AI, CATEGORY_SPAM
from src.models import EmailMessage


def make_email(**overrides) -> EmailMessage:
    defaults = dict(
        id="1",
        subject="Hej",
        sender_name="Kalle",
        sender_address="kalle@example.com",
        body_preview="",
        received_at="2026-01-01T00:00:00Z",
        mailbox="petter.edlund@movedigital.se",
        has_list_unsubscribe=False,
    )
    defaults.update(overrides)
    return EmailMessage(**defaults)


def test_no_match_for_plain_personal_email():
    email = make_email(subject="Lunch imorgon?", body_preview="Har du tid på fredag?")
    assert rules.evaluate(email) is None


def test_detects_ai_related_domain():
    email = make_email(subject="Din faktura", sender_address="billing@anthropic.com")
    match = rules.evaluate(email)
    assert match is not None
    assert match.category == CATEGORY_AI


def test_advertising_and_ai_content_defers_to_llm():
    # Regelmotorn gissar inte längre på Reklam vs. AI-relaterat - även ett
    # tydligt nyhetsbrev med AI-innehåll ska lämnas obestämt (None) så Claude
    # gör den bedömningen med hela mejlinnehållet som underlag.
    email = make_email(
        subject="AI's creative funding continues",
        sender_address="newsletter@example.com",
        body_preview="Sign up for our newsletter to stay updated",
        has_list_unsubscribe=True,
    )
    assert rules.evaluate(email) is None


def test_detects_spam_keywords():
    email = make_email(
        subject="DU HAR VUNNIT ett pris!!!",
        body_preview="Klicka här för att lösa in din vinst, gratis pengar väntar",
    )
    match = rules.evaluate(email)
    assert match is not None
    assert match.category == CATEGORY_SPAM
