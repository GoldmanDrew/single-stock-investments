from _system.trading.portfolio_hub.publisher import signed_headers


def test_signed_headers_are_body_bound() -> None:
    headers = signed_headers("x" * 32, b"payload", now=1_777_777_777)
    assert headers["x-portfolio-timestamp"] == "1777777777"
    assert headers["user-agent"] == "MagisPortfolioHub/1.0"
    assert len(headers["x-portfolio-nonce"]) == 32
    assert len(headers["x-portfolio-signature"]) == 64
