import smtplib

import pytest

from src.mailer import send_email

CFG = {"email": {"to": "your-email@example.com", "from": "your-email@example.com",
                 "smtp_host": "smtp.qq.com", "smtp_port": 465}}


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.logged_in = None
        self.sent = None
        FakeSMTP.instances.append(self)

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_send_email_uses_ssl_qq_and_same_from_to(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    send_email("主题", "<p>hi</p>", CFG, "authcode")
    s = FakeSMTP.instances[0]
    assert (s.host, s.port) == ("smtp.qq.com", 465)
    assert s.logged_in == ("your-email@example.com", "authcode")
    assert s.sent["From"] == "your-email@example.com"
    assert s.sent["To"] == "your-email@example.com"


def test_send_email_raises_when_login_fails(monkeypatch):
    class Bad(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad auth")

    monkeypatch.setattr(smtplib, "SMTP_SSL", Bad)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        send_email("s", "<p>x</p>", CFG, "wrong")
