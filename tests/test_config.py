import base64
import os

import pytest

from conftest import BASE, PASSWORD, USER
from wp_post.client import WordPressClient
from wp_post.config import env_file_problems, load_config, require_credentials
from wp_post.errors import ConfigError
from wp_post.redaction import REDACTED, redact, register_secret


def test_environment_beats_env_file(repo):
    (repo / ".wp-post.env").write_text(
        "# comment\nexport WP_USERNAME=fileuser\nWP_APPLICATION_PASSWORD='file pass word'\n"
    )
    cfg = load_config(repo, {"WP_USERNAME": "envuser"}, keychain=None)
    assert cfg.username == "envuser" and cfg.sources["WP_USERNAME"] == "environment"
    assert cfg.password == "file pass word"
    assert cfg.sources["WP_APPLICATION_PASSWORD"] == ".wp-post.env"
    assert cfg.site_url == BASE and cfg.sources["WP_SITE_URL"] == "_config.yml"
    assert "file pass word" not in repr(cfg)


def test_keychain_used_only_when_password_missing(repo):
    calls = []

    def keychain(service, account):
        calls.append((service, account))
        return "from keychain"

    cfg = load_config(repo, {"WP_USERNAME": "u"}, keychain=keychain)
    assert cfg.password == "from keychain" and calls == [("wp-post", "u")]
    cfg = load_config(repo, {"WP_USERNAME": "u", "WP_APPLICATION_PASSWORD": "envpass"}, keychain)
    assert cfg.password == "envpass" and len(calls) == 1


def test_missing_credentials_is_a_config_error(repo):
    cfg = load_config(repo, {}, keychain=None)
    with pytest.raises(ConfigError) as exc:
        require_credentials(cfg)
    assert exc.value.exit_code == 4
    assert "WP_USERNAME" in exc.value.message and "WP_APPLICATION_PASSWORD" in exc.value.message


@pytest.mark.parametrize("url", ["http://blog.example", "ftp://x", "https://blog.example/sub"])
def test_site_url_must_be_https_root(repo, url):
    with pytest.raises(ConfigError):
        load_config(repo, {"WP_SITE_URL": url}, keychain=None)


def test_malformed_env_file(repo):
    (repo / ".wp-post.env").write_text("WP_USERNAME\n")
    with pytest.raises(ConfigError, match="KEY=VALUE"):
        load_config(repo, {}, keychain=None)


def test_world_readable_env_file_is_flagged(repo):
    path = repo / ".wp-post.env"
    path.write_text("WP_USERNAME=u\n")
    os.chmod(path, 0o644)
    assert env_file_problems(path)
    os.chmod(path, 0o600)
    assert env_file_problems(path) == []


def test_redaction_covers_spaced_compact_and_basic_token():
    register_secret("abcd efgh ijkl")
    token = base64.b64encode(b"u:abcd efgh ijkl").decode()
    from wp_post.redaction import register_basic_auth

    register_basic_auth("u", "abcd efgh ijkl")
    text = redact(f"a abcd efgh ijkl b abcdefghijkl c {token}")
    assert "abcd" not in text and token not in text and text.count(REDACTED) == 3


def test_api_error_messages_are_redacted(fake):
    """Even if a server echoed the credential back, it must not reach output."""
    client = WordPressClient(BASE, USER, PASSWORD, session=fake)
    fake.route = lambda *a, **k: __import__("conftest").FakeResponse(
        500, {"code": "boom", "message": f"bad header {fake.auth} / {PASSWORD}"}
    )
    with pytest.raises(Exception) as exc:
        client.get("/wp/v2/posts")
    assert PASSWORD not in str(exc.value.message)
    assert fake.auth.split()[1] not in str(exc.value.message)


def test_cli_never_prints_the_password(run, fake):
    fake.auth = "Basic wrong"  # make every authenticated call fail
    for argv in (["doctor"], ["sync", "_drafts/a.md"], ["list"]):
        (run.repo / "_drafts/a.md").write_text('---\ntitle: "A"\n---\nx\n')
        code, out, err = run(*argv)
        assert code == 4, (argv, out, err)
        for secret in (PASSWORD, PASSWORD.replace(" ", "")):
            assert secret not in out + err
    assert "Authentication failed" in err


def test_password_never_in_argv_or_url(run, fake):
    (run.repo / "_drafts/a.md").write_text('---\ntitle: "A"\n---\nx\n')
    run("sync", "_drafts/a.md")
    for req in fake.requests:
        assert PASSWORD not in req["url"] and PASSWORD not in str(req["params"])
