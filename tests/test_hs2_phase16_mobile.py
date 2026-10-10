import unittest
from flask import Flask
from hs2_supermap.api import create_blueprint,WEB
from hs2_supermap.mobile import mobile_shell
from hs2_design.domain import ContractError
from hs2_help.content import content


class SharedMobile(unittest.TestCase):
    def test_shared_shell_not_separate_prices_layers_or_fake_content(self):
        html=(WEB/"search.html").read_text();mobile=mobile_shell(html)
        self.assertIn('data-mobile-view="list"',mobile)
        for name in ("search.js","controller.js","listingList","mapCanvas","stay","auction"):
            self.assertIn(name,html);self.assertIn(name,mobile)
        self.assertNotIn("api/results",mobile) # Original controller owns data.
        with self.assertRaises(ContractError):mobile_shell("<html>invented approximation</html>")
        self.assertEqual(content()["guides"][0]["uri"],"/hs2/search/")

    def test_route_and_original_shell_share_no_store_but_separate_presentation(self):
        app=Flask(__name__);app.register_blueprint(create_blueprint(object(),map_config=lambda:{},allow_request=lambda:True))
        client=app.test_client();normal=client.get("/hs2/search/");mobile=client.get("/hs2/search/mobile/")
        self.assertEqual(normal.status_code,200);self.assertEqual(mobile.status_code,200)
        self.assertNotIn('data-mobile-experience="true"',normal.text);self.assertIn('data-mobile-experience="true"',mobile.text)
        self.assertEqual(mobile.headers["Cache-Control"],"no-store")
        self.assertEqual(client.get("/hs2/search/assets/mobile.js").status_code,200)
        self.assertEqual(client.get("/hs2/search/assets/mobile.css").status_code,200)


if __name__=="__main__":unittest.main()
