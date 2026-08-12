"""End-to-end wire-format tests for the email notifier.

These tests spin up a minimal in-process SMTP server (stdlib only) that captures
the exact bytes the notifier puts on the wire, then re-parse those bytes the way
a compliant mail client would and assert the recovered content matches what was
sent.

Purpose: a user reported receiving the email body as raw base64 text instead of
decoded plain text. This suite verifies whether the message the notifier
produces is well-formed: a compliant client parsing the transmitted bytes must
recover the original subject and body. If these tests pass, the raw text the
user saw is a problem on the *receiving* side (non-compliant client / upstream
relay), not in this repository.

The tests do not assert on the transfer encoding directly — they only check that
the delivered content equals the sent content, which implicitly covers whatever
encoding the notifier chooses.
"""

import email
import socket
import threading
from email import policy

from app.config import EmailConfig
from app.notification.email_notifier import EmailNotifier

# The exact body the user reported receiving as raw base64.
REPORTED_BODY = (
    "Appointments are now available for MVZ Dr. Hasert Lichtenberg!\n\n"
    "  - 2026-11-12T08:30:00.000+01:00\n"
    "  - 2026-11-12T08:45:00.000+01:00\n"
    "  ... and 11 more\n\n"
    "Book now: https://www.doctolib.de/hautarzt/berlin/mvz-dr-hasert-gmbh-"
    "standort-lichtenberg/booking/availabilities?specialityId=1289\n"
    "Doctor profile: https://www.doctolib.de/hautarzt/berlin/mvz-dr-hasert-"
    "gmbh-standort-lichtenberg\n\n"
    "Have a nice day!\nYour friendly Robot Assistant"
)


class _MockSMTPServer:
    """A minimal, single-connection SMTP server that captures the raw DATA.

    Speaks just enough of RFC 5321 to let smtplib complete a session:
    greeting, EHLO/HELO, MAIL FROM, RCPT TO, DATA (dot-terminated), QUIT.
    Runs in a background thread and records the raw message bytes.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.host, self.port = self._sock.getsockname()
        self.raw_message: bytes = b""
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> "_MockSMTPServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._thread.join(timeout=5)
        self._sock.close()

    def _serve(self) -> None:
        conn, _ = self._sock.accept()
        with conn:
            f = conn.makefile("rb")
            conn.sendall(b"220 mock.smtp.local ESMTP\r\n")
            in_data = False
            data_lines: list[bytes] = []
            while True:
                line = f.readline()
                if not line:
                    break
                if in_data:
                    if line in (b".\r\n", b".\n"):
                        # De-transparency: strip leading dot on dot-stuffed lines.
                        unstuffed = [
                            ln[1:] if ln.startswith(b"..") else ln
                            for ln in data_lines
                        ]
                        self.raw_message = b"".join(unstuffed)
                        conn.sendall(b"250 OK message accepted\r\n")
                        in_data = False
                        data_lines = []
                        continue
                    data_lines.append(line)
                    continue

                upper = line.upper()
                if upper.startswith(b"EHLO"):
                    conn.sendall(b"250-mock.smtp.local\r\n250 HELP\r\n")
                elif upper.startswith(b"HELO"):
                    conn.sendall(b"250 mock.smtp.local\r\n")
                elif upper.startswith((b"MAIL", b"RCPT")):
                    conn.sendall(b"250 OK\r\n")
                elif upper.startswith(b"DATA"):
                    conn.sendall(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    in_data = True
                elif upper.startswith(b"QUIT"):
                    conn.sendall(b"221 Bye\r\n")
                    break
                elif upper.startswith(b"RSET"):
                    conn.sendall(b"250 OK\r\n")
                else:
                    conn.sendall(b"250 OK\r\n")


def _make_config(host: str, port: int) -> EmailConfig:
    return EmailConfig.model_validate(
        {
            "smtp_host": host,
            "smtp_port": port,
            "username": "",
            "password": "",
            "from_address": "from@example.com",
            "to_addresses": ["to@example.com"],
            "use_tls": False,
        }
    )


def _send_and_parse(subject: str, body: str) -> email.message.EmailMessage:
    """Send a message through the notifier and parse it as a client would."""
    with _MockSMTPServer() as server:
        config = _make_config(server.host, server.port)
        EmailNotifier(config).notify(subject, body)
        raw = server.raw_message
    assert raw, "mock SMTP server captured no message bytes"
    return email.message_from_bytes(raw, policy=policy.default)


def _delivered_body(parsed: email.message.EmailMessage) -> str:
    part = parsed.get_body(preferencelist=("plain",))
    assert part is not None, "no text/plain part found in delivered message"
    return part.get_content()


def test_delivered_body_matches_sent_body():
    """A client parsing the transmitted bytes recovers the original body.

    This is the crux: if this passes, the message is well-formed and the raw
    base64 the user saw is a receiving-side (client/relay) issue, NOT a bug in
    this repo.
    """
    parsed = _send_and_parse("Subject", REPORTED_BODY)
    assert _delivered_body(parsed).rstrip("\n") == REPORTED_BODY.rstrip("\n")


def test_delivered_subject_matches_sent_subject():
    parsed = _send_and_parse("Appointments available!", REPORTED_BODY)
    assert parsed["Subject"] == "Appointments available!"


def test_delivered_body_survives_unicode():
    """Non-ASCII content must round-trip intact through transport encoding."""
    body = "Termine verfügbar für Dr. Müller — Grüße! 你好 😀"
    parsed = _send_and_parse("Ünïcödé Sübject", body)
    assert _delivered_body(parsed).rstrip("\n") == body
    assert parsed["Subject"] == "Ünïcödé Sübject"


def test_delivered_headers_match():
    parsed = _send_and_parse("Subject", "short body")
    assert parsed["From"] == "from@example.com"
    assert "to@example.com" in parsed["To"]


def test_body_is_readable_on_the_wire_not_base64():
    """Regression: the plaintext must travel human-readable, not base64.

    A relay (observed with Mailjet) re-templated a base64-encoded text/plain
    part without decoding it first, embedding the raw base64 as literal body
    text so the recipient saw an undecoded blob. Guard against that by ensuring
    the readable text appears verbatim in the transmitted bytes and the part is
    NOT base64-encoded.
    """
    with _MockSMTPServer() as server:
        config = _make_config(server.host, server.port)
        EmailNotifier(config).notify("Subject", REPORTED_BODY)
        raw = server.raw_message
    assert raw

    parsed = email.message_from_bytes(raw, policy=policy.default)
    part = parsed.get_body(preferencelist=("plain",))
    cte = (part["Content-Transfer-Encoding"] or "").lower()
    assert cte != "base64", f"body was base64-encoded on the wire (CTE={cte!r})"

    # A distinctive ASCII sentence from the body must be readable in the raw
    # bytes (quoted-printable leaves plain ASCII untouched).
    assert b"Appointments are now available" in raw
