import unittest

from src.demo import load_demo
from src.youtube import YouTubeError, parse_video_id


class YouTubeUrlTest(unittest.TestCase):
    def test_watch_url(self):
        self.assertEqual(parse_video_id("https://www.youtube.com/watch?v=77nP8lcSuzY&xstg=abc"), "77nP8lcSuzY")

    def test_short_url(self):
        self.assertEqual(parse_video_id("https://youtu.be/77nP8lcSuzY"), "77nP8lcSuzY")

    def test_bare_id(self):
        self.assertEqual(parse_video_id("77nP8lcSuzY"), "77nP8lcSuzY")

    def test_not_youtube(self):
        with self.assertRaises(YouTubeError):
            parse_video_id("https://example.com/watch?v=77nP8lcSuzY")


class DemoTest(unittest.TestCase):
    def test_demo_shape(self):
        d = load_demo()
        self.assertEqual(d["chat"]["n_msgs"], 2008)
        self.assertEqual(len(d["quotes"]), 9)
        self.assertTrue(d["network"]["nodes"])
        # 저장된 결과에 채팅 원문이나 닉네임이 없어야 한다
        self.assertNotIn("authorName", str(d))


if __name__ == "__main__":
    unittest.main()
