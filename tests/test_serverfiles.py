from craftyvecta.serverfiles import yaml_replace

VELOCITY = ("proxies", "velocity", "enabled")


def test_replaces_only_the_exact_path():
    text = "proxies:\n  bungee-cord:\n    velocity:\n      enabled: true\n  velocity:\n    enabled: false\n"
    assert yaml_replace(text, VELOCITY, "true", "false") == (text, False)
    expected = "proxies:\n  bungee-cord:\n    velocity:\n      enabled: true\n  velocity:\n    enabled: true\n"
    assert yaml_replace(text, VELOCITY, "false", "true") == (expected, True)


def test_keeps_comments_quotes_blank_lines_and_crlf():
    text = "# Paper\r\nproxies:\r\n  # velocity\r\n  'velocity':\r\n\r\n    enabled: true  # modern forwarding\r\n"
    assert yaml_replace(text, VELOCITY, "true", "false") == (text.replace("enabled: true", "enabled: false"), True)


def test_nested_or_missing_keys_are_not_matched():
    text = "other:\n  settings:\n    bungeecord: true\nsettings:\n  timeout-time: 60\n"
    assert yaml_replace(text, ("settings", "bungeecord"), "true", "false") == (text, False)
    assert yaml_replace("", ("settings", "bungeecord"), "true", "false") == ("", False)
