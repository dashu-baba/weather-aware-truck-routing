from planner.cache import cache_key


def test_same_payload_gives_same_key():
    assert cache_key("geo:", ["dallas", False]) == cache_key("geo:", ["dallas", False])


def test_dict_key_order_does_not_matter():
    assert cache_key("p:", {"a": 1, "b": 2}) == cache_key("p:", {"b": 2, "a": 1})


def test_different_payload_gives_different_key():
    assert cache_key("geo:", ["dallas", False]) != cache_key("geo:", ["dallas", True])


def test_prefix_is_kept_and_separates_namespaces():
    key = cache_key("geo:", ["x"])
    assert key.startswith("geo:")
    assert key != cache_key("plan:", ["x"])
