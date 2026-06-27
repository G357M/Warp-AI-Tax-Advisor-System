import sys
import os
import unittest

# Add the current directory to sys.path to allow importing infohub_native_api
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infohub_native_api import score_candidate_body, html_fragment_to_markdown

class TestParserRegression(unittest.TestCase):

    def test_source_selection(self):
        # Case 1: Richer description wins over chrome-heavy additionalDescription
        detail = {
            "markdown": "too short",
            "description": "მუხლი 1. ტექსტი",
            "additionalDescription": "ჩამოტვირთვა გაზიარება"
        }
        result = score_candidate_body(detail)
        self.assertEqual(result["selected_field"], "description")
        self.assertIn("მუხლი 1", result["selected_value"])

    def test_chrome_stripping(self):
        # Case 2: Chrome stripping removes specific tokens
        html = "მუხლი 1. ტექსტი ჩამოტვირთვა გაზიარება"
        md = html_fragment_to_markdown(html)
        self.assertNotIn("ჩამოტვირთვა", md)
        self.assertNotIn("გაზიარება", md)
        self.assertIn("მუხლი 1. ტექსტი", md)

    def test_anchor_handling(self):
        # Case 3: Anchor handling preserves href as markdown link
        html = '<a href="https://example.com">Link</a>'
        md = html_fragment_to_markdown(html)
        self.assertIn("[Link](https://example.com)", md)

    def test_base64_image_handling(self):
        # Case 4: Base64 img does not dump raw data
        html = '<img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==" alt="test-img">'
        md = html_fragment_to_markdown(html)
        self.assertIn("[Image (base64): test-img]", md)
        self.assertNotIn("iVBORw0KGgoAAAANSUhEUg", md)

    def test_simple_table_rendering(self):
        # Case 5: Simple table renders with visible row/cell structure
        html = '<table><tr><th>Header 1</th><th>Header 2</th></tr><tr><td>Cell 1</td><td>Cell 2</td></tr></table>'
        md = html_fragment_to_markdown(html)
        self.assertIn("| Header 1 | Header 2 |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| Cell 1 | Cell 2 |", md)

    def test_ordered_list_rendering(self):
        # Case 6: Ordered list remains visibly ordered
        html = '<ol><li>First item</li><li>Second item</li></ol>'
        md = html_fragment_to_markdown(html)
        self.assertIn("1. First item", md)
        self.assertIn("2. Second item", md)

    def test_legal_heading_promotion(self):
        # Case 7: Bold legal headings are promoted to markdown headings
        # and ordinary bold text remains bold.
        html = '<strong>მუხლი 1. ტესტური სათაური</strong> <b>ჩვეულებრივი ტექსტი</b>'
        md = html_fragment_to_markdown(html)
        
        # Check heading promotion (მუხლი -> # level 4)
        self.assertIn("#### მუხლი 1. ტესტური სათაური", md)
        
        # Check ordinary bold preservation
        self.assertIn("**ჩვეულებრივი ტექსტი**", md)

if __name__ == "__main__":
    unittest.main()
