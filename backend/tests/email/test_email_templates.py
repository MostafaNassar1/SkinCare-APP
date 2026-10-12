from app.scripts import send_test_email
from app.services import email_service
from app.services.email_templates import password_reset_code_email, verification_code_email


def test_verification_email_contains_the_code_everywhere():
    email = verification_code_email("aya@gmail.com", "Aya", "482913", minutes=10)

    assert email.to == "aya@gmail.com"
    assert email.subject == "482913 is your SkinCare verification code"
    assert "482913" in email.text and "482913" in email.html
    assert "10 minutes" in email.text and "10 minutes" in email.html
    assert "verify your email" in email.text


def test_reset_email_says_what_it_is_for():
    email = password_reset_code_email("aya@gmail.com", "Aya", "111222", minutes=10)

    assert "password reset" in email.subject
    assert "new password" in email.text


def test_user_name_cannot_inject_html():
    name = '<a href="https://evil.example">Click here</a>'
    email = verification_code_email("aya@gmail.com", name, "482913", minutes=10)

    assert "<a href" not in email.html
    assert "&lt;a href=" in email.html


# ---------- send_test_email command ----------


def test_send_test_email_in_console_mode(outbox, capsys):
    assert send_test_email.main(["--to", "aya@gmail.com"]) == 0

    assert outbox[0].to == "aya@gmail.com"
    assert "Console mode" in capsys.readouterr().out


def test_send_test_email_shows_the_error(monkeypatch, capsys):
    def broken(email):
        raise OSError("Username and Password not accepted")

    monkeypatch.setattr(email_service, "_deliver", broken)

    assert send_test_email.main(["--to", "aya@gmail.com"]) == 1
    assert "Username and Password not accepted" in capsys.readouterr().err
