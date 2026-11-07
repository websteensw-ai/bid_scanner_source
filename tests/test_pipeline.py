import pathlib
import unittest

from kiwipiepy import Kiwi

from src.pipeline import (analyze, anonymize, chat_quotes_check, classify,
                          parse_chat_jsonl, parse_vtt)

FIX = pathlib.Path(__file__).parent / "fixtures"


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.kiwi = Kiwi()

    def test_vtt_dedup_and_tags(self):
        segs = parse_vtt((FIX / "sample.vtt").read_text(encoding="utf-8"))
        texts = [s.text for s in segs]
        self.assertEqual(texts.count("장수 한우 품질이 최고입니다"), 1)
        self.assertFalse(any("[음악]" in t for t in texts))

    def test_chat_parse_and_anonymize(self):
        chat = parse_chat_jsonl((FIX / "sample_chat.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(len(chat), 5)
        anonymize(chat)
        self.assertTrue(all(m.author == "" for m in chat))
        self.assertIn("U001", {m.author_id for m in chat})

    def test_classify(self):
        self.assertEqual(classify("완판 가즈아"), "판매 응원(완판)")
        self.assertEqual(classify("구매 링크 어디요"), "구매 언급")
        self.assertEqual(classify("날씨가 좋네요"), "기타")

    def test_analyze_runs(self):
        segs = parse_vtt((FIX / "sample.vtt").read_text(encoding="utf-8"))
        chat = parse_chat_jsonl((FIX / "sample_chat.jsonl").read_text(encoding="utf-8"))
        anonymize(chat)
        res = analyze(segs, chat, self.kiwi, min_edge=1)
        self.assertTrue(res.term_freq)
        self.assertTrue(res.graph_nodes)
        # 가짜 데이터는 변동이 적어 상관을 계산하지 못할 수 있다. 계산되면 범위만 확인.
        self.assertTrue(res.correlation is None or -1 <= res.correlation <= 1)

    def test_quote_check(self):
        chat = parse_chat_jsonl((FIX / "sample_chat.jsonl").read_text(encoding="utf-8"))
        out = chat_quotes_check(chat, ["완판 가즈아", "없는 문구"])
        self.assertEqual(out[0]["count"], 1)
        self.assertEqual(out[1]["count"], 0)


if __name__ == "__main__":
    unittest.main()
