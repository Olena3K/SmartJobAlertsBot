"""Offline tests with synthetic HTML (no network needed). Run: python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workua_parser import build_search_url, normalize_query, parse_jobs  # noqa: E402

SAMPLE = """
<div id="pjax-jobs-list">
  <div class="card card-hover card-search">
    <h2 class="my-0"><a href="/jobs/4878388/" title="x">Junior Python Engineer</a></h2>
    <div><b>20&nbsp;000 грн</b></div><a href="/jobs/4878388/"><img></a>
  </div>
  <div class="card job-link">
    <h2><a href="/en/jobs/111/">Senior <span>Python</span> Dev</a></h2>
    <div>25 000 – 40 000 UAH · After all deductions</div>
  </div>
  <div class="card"><h2><a href="/jobs/222/">No salary job</a></h2></div>
  <h2><a href="/jobs/by-category/">Not a job</a></h2>
  <h2><a href="/jobs/4878388/">Duplicate</a></h2>
</div>
"""


class ParserTests(unittest.TestCase):
    def test_parse(self):
        jobs = parse_jobs(SAMPLE, 10)
        self.assertEqual([j.url for j in jobs], [
            "https://www.work.ua/jobs/4878388/",
            "https://www.work.ua/jobs/111/",
            "https://www.work.ua/jobs/222/",
        ])
        self.assertEqual(jobs[0].title, "Junior Python Engineer")
        self.assertEqual(jobs[0].salary, "20 000 грн")
        self.assertEqual(jobs[1].title, "Senior Python Dev")
        self.assertIn("UAH", jobs[1].salary)
        self.assertIsNone(jobs[2].salary)

    def test_limit(self):
        self.assertEqual(len(parse_jobs(SAMPLE, 2)), 2)

    def test_fallback_without_headings(self):
        html = '<div><a href="/jobs/5/">Plain link job</a></div>'
        self.assertEqual(parse_jobs(html)[0].title, "Plain link job")

    def test_empty(self):
        self.assertEqual(parse_jobs("<html></html>"), [])

    def test_query(self):
        self.assertEqual(normalize_query("  Junior   Python  "), "junior python")
        self.assertEqual(build_search_url("junior python"), "https://www.work.ua/jobs-junior+python/")
        self.assertIn("%D0%BF", build_search_url("продавець"))


if __name__ == "__main__":
    unittest.main()
