import json
import urllib.error
import urllib.request

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from sharei import push, server

ENDPOINT = "https://push.example.net/push/abc"


def subscription(endpoint=ENDPOINT):
    browser = ec.generate_private_key(ec.SECP256R1())
    return {
        "endpoint": endpoint,
        "keys": {
            "p256dh": push.b64url(push.public_bytes(browser)),
            "auth": push.b64url(b"0123456789abcdef"),
        },
    }


def post_json(url, payload, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(request) as response:
        return response.headers, json.load(response)


@pytest.fixture
def push_server(live_server, monkeypatch):
    monkeypatch.setattr(server, "PUSH_ENABLED", True)
    monkeypatch.setattr(push, "host_is_public", lambda host: True)
    return live_server


def test_encrypt_matches_rfc8291_example():
    decode = push.b64url_decode
    sender = ec.derive_private_key(
        int.from_bytes(decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw")),
        ec.SECP256R1(),
    )
    body = push.encrypt(
        b"When I grow up, I want to be a watermelon",
        decode(
            "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
        ),
        decode("BTBZMqHH6r4Tts7J_aSIgg"),
        salt=decode("DGv6ra1nlYgDCS1FRnbzlw"),
        server_key=sender,
    )
    assert push.b64url(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6Tlz"
        "AC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_vapid_authorization_is_signed_for_the_push_origin(tmp_path):
    key = push.load_key(tmp_path / "vapid.pem")
    assert (tmp_path / "vapid.pem").stat().st_mode & 0o777 == 0o600
    assert push.public_bytes(
        push.load_key(tmp_path / "vapid.pem")
    ) == push.public_bytes(key)
    header = push.vapid_authorization(key, ENDPOINT, "mailto:me@example.com", now=1000)
    token, public = header.removeprefix("vapid t=").split(", k=")
    assert push.b64url_decode(public) == push.public_bytes(key)
    head, claims, signature = token.split(".")
    assert json.loads(push.b64url_decode(claims)) == {
        "aud": "https://push.example.net",
        "exp": 1000 + 12 * 3600,
        "sub": "mailto:me@example.com",
    }
    raw = push.b64url_decode(signature)
    key.public_key().verify(
        encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:])),
        f"{head}.{claims}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://push.example.net/x",
        "https://user@push.example.net/x",
        "https://push.example.net:8443/x",
        "https://10.0.0.1/x",
        "https://[::1]/x",
        "https://localhost/x",
        "https:///x",
        12,
    ],
)
def test_endpoint_refused(endpoint):
    assert not push.endpoint_allowed(endpoint)


def test_push_routes_hidden_without_cryptography(live_server):
    for path in ("/sw.js", "/push/key"):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(live_server + path)
        assert error.value.code == 404
    with urllib.request.urlopen(live_server + "/drop") as response:
        assert b'<button type="button" data-push' not in response.read()


def test_subscribe_and_unsubscribe(push_server):
    with urllib.request.urlopen(push_server + "/push/key") as response:
        assert len(push.b64url_decode(json.load(response)["key"])) == 65
    with urllib.request.urlopen(push_server + "/sw.js") as response:
        assert b"showNotification" in response.read()
    with urllib.request.urlopen(push_server + "/drop") as response:
        assert b'<button type="button" data-push' in response.read()

    headers, body = post_json(push_server + "/push/subscribe", subscription())
    assert body["id"] == server.push_id(ENDPOINT)
    assert f"sharei-push={body['id']};" in headers["Set-Cookie"]
    assert "HttpOnly" in headers["Set-Cookie"]
    assert list(server.push_subs_locked()) == [body["id"]]

    bad = subscription()
    bad["keys"]["auth"] = push.b64url(b"short")
    for payload in (
        bad,
        subscription("http://push.example.net/x"),
        {"endpoint": ENDPOINT},
    ):
        with pytest.raises(urllib.error.HTTPError) as error:
            post_json(push_server + "/push/subscribe", payload)
        assert error.value.code == 400

    _, body = post_json(push_server + "/push/unsubscribe", {"endpoint": ENDPOINT})
    assert body == {"removed": True}
    assert server.push_subs_locked() == {}


def test_uploads_and_clip_queue_notifications(push_server):
    _, body = post_json(push_server + "/push/subscribe", subscription())
    cookie = f"sharei-push={body['id']}"
    for name in ("a.pdf", "b.txt"):
        request = urllib.request.Request(
            f"{push_server}/upload?name={name}",
            data=b"x",
            headers={"Cookie": cookie},
            method="POST",
        )
        urllib.request.urlopen(request).close()
    request = urllib.request.Request(
        push_server + "/clip",
        data=b"  hello\n  world  ",
        headers={"Content-Type": "text/plain"},
        method="POST",
    )
    urllib.request.urlopen(request).close()

    notes = dict(server.push_take_due(float("inf")))
    assert notes["drop"]["count"] == 2 and notes["drop"]["skip"] == body["id"]
    assert json.loads(server.push_payload("drop", notes["drop"])) == {
        "title": "2 new files",
        "body": "b.txt",
        "url": "/drop",
        "tag": "drop",
    }
    assert notes["clip"]["skip"] is None
    assert (
        json.loads(server.push_payload("clip", notes["clip"]))["body"] == "hello world"
    )


def test_deliver_skips_sender_and_drops_expired(push_server, monkeypatch):
    first = subscription("https://push.example.net/one")
    second = subscription("https://push.example.net/two")
    third = subscription("https://push.example.net/three")
    for sub in (first, second, third):
        post_json(push_server + "/push/subscribe", sub)
    sent = []

    def fake_send(sub, payload, key, subject, topic=""):
        sent.append(sub["endpoint"])
        return 410 if sub["endpoint"].endswith("/two") else 201

    monkeypatch.setattr(push, "send", fake_send)
    server.push_notify(
        "clip", "Clipboard", "Clipboard", "hi", server.push_id(first["endpoint"])
    )
    ((tag, note),) = server.push_take_due(float("inf"))
    server.push_deliver(tag, note)
    assert sent == [second["endpoint"], third["endpoint"]]
    assert sorted(server.push_subs_locked()) == sorted(
        server.push_id(sub["endpoint"]) for sub in (first, third)
    )


def test_subscriptions_are_capped(push_server, monkeypatch):
    monkeypatch.setattr(server, "PUSH_SUBS_MAX", 2)
    for name in ("one", "two", "three"):
        post_json(
            push_server + "/push/subscribe", subscription(f"https://p.example/{name}")
        )
    assert sorted(server.push_subs_locked()) == sorted(
        server.push_id(f"https://p.example/{name}") for name in ("two", "three")
    )
