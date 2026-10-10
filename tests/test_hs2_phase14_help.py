import unittest
from hs2_help.content import content,CONSUMER,OPERATOR,SPECIAL
from hs2_help.fixture_http import app


class HelpContent(unittest.TestCase):
    def test_original_scope_all_topics_and_unique_first_party_content(self):
        body=content()
        self.assertEqual(len(CONSUMER),24);self.assertEqual(len(OPERATOR),23);self.assertEqual(len(SPECIAL),12)
        self.assertEqual(len(body["faqs"]),59);self.assertEqual(len({f["id"] for f in body["faqs"]}),59)
        for f in body["faqs"]:
            self.assertTrue(f["question"].endswith("?"))
            self.assertGreater(len(f["answer"]),45)
            self.assertNotIn("<script",f["answer"])
        self.assertFalse(body["live_operations_approved"])
        self.assertEqual(len(body["guides"]),3);self.assertEqual(len(body["policies"]),3)
        self.assertEqual(content()["version"],body["version"])

    def test_policy_truth_unknown_costs_and_legacy_docs_not_replaced(self):
        self.assertIn("0%",OPERATOR["수수료"][1]);self.assertIn("PG",OPERATOR["수수료"][1])
        self.assertIn("최소7일",CONSUMER["날짜"][1]);self.assertIn("최소1박",CONSUMER["날짜"][1])
        self.assertIn("실제 환불",CONSUMER["환불"][1]);self.assertIn("실제 결제",CONSUMER["예약확정"][1])
        links={p.get("uri") for p in content()["policies"]}
        self.assertIn("/terms",links);self.assertIn("/privacy",links)
        self.assertIn("초기",content()["policies"][0]["title"])

    def test_actual_api_search_audiences_empty_and_malformed_explicit(self):
        client=app().test_client()
        r=client.get("/hs2/help/api/content")
        self.assertEqual(r.status_code,200);self.assertEqual(r.headers["Cache-Control"],"no-store")
        self.assertEqual(len(r.get_json()["faqs"]),59)
        self.assertEqual(len(client.get("/hs2/help/api/content?audience=operator").get_json()["faqs"]),23)
        found=client.get("/hs2/help/api/content?audience=operator&q=수수료").get_json()["faqs"]
        self.assertEqual(len(found),2)
        self.assertEqual(client.get("/hs2/help/api/content?q=no-match-synthetic").get_json()["faqs"],[])
        for uri in ["?user_id=101","?audience=other","?q="+"x"*81]:
            self.assertEqual(client.get("/hs2/help/api/content"+uri).status_code,400)


if __name__=="__main__":unittest.main()
