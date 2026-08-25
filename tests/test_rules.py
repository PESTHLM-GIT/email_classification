from src import rules
from src.config import CATEGORY_ADS, CATEGORY_AI, CATEGORY_SPAM
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


def test_detects_advertising_with_unsubscribe_header():
    email = make_email(
        subject="Stor REA denna helg - 30% rabatt",
        sender_address="nyhetsbrev@butik.se",
        body_preview="Missa inte vårt erbjudande",
        has_list_unsubscribe=True,
    )
    match = rules.evaluate(email)
    assert match is not None
    assert match.category == CATEGORY_ADS
    assert match.confidence >= 0.85


def test_detects_ai_related_domain():
    email = make_email(subject="Din faktura", sender_address="billing@anthropic.com")
    match = rules.evaluate(email)
    assert match is not None
    assert match.category == CATEGORY_AI


def test_detects_ai_related_keywords():
    email = make_email(
        subject="Nyhetsbrev om maskininlärning och generativ AI",
        sender_address="redaktion@techmedia.se",
        body_preview="Den här veckan: nya rön inom machine learning",
    )
    match = rules.evaluate(email)
    assert match is not None
    assert match.category == CATEGORY_AI


def test_ai_signal_prevents_blind_ad_short_circuit():
    # Verkligt fall: "AI's creative funding continues" missades tidigare av
    # AI-regeln (bokstavligt " ai " matchar inte "AI's" - ingen mellanslag
    # runt ordet), och föll då rakt igenom till Reklam-regeln bara för att
    # det var ett nyhetsbrev med List-Unsubscribe. Nu ska ett AI-signalord
    # stoppa det blinda Reklam-antagandet och lämna avgörandet till Claude.
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
