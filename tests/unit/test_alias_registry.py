from linkrag_eval.retrieval.aliases import AliasRegistry


def test_domain_alias_expansion_and_ambiguity_protection() -> None:
    registry=AliasRegistry({"version":"2026.07.1","domains":{"payments":{
        "ambiguous_aliases":["卡"],
        "entries":[{"canonical":"银行卡","aliases":["储蓄卡","卡"]}],
    }}})
    result=registry.expand("银行卡限额",domain="payments")
    assert result.expanded_query == "银行卡限额 储蓄卡"
    assert result.blocked_ambiguous == ("卡",)
    assert registry.expand("银行卡限额",domain="unknown").expanded_query == "银行卡限额"
