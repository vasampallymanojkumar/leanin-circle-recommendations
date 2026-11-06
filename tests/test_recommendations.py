import json
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from app import make_handler
from recommender import SNAPSHOT_DATE, connect, recommend, seed


class RecommendationsTest(unittest.TestCase):
    def setUp(self):
        self.db = connect()
        seed(self.db)

    def tearDown(self):
        self.db.close()

    def ids(self, user, limit=5):
        return [c['id'] for c in recommend(self.db, user, limit)['recommendations']]

    def test_cold_start_is_active_diverse_and_deterministic(self):
        result = recommend(self.db, 42)
        self.assertEqual(result, recommend(self.db, 42))
        self.assertEqual(len(result['recommendations']), 5)
        topics = [c['topic'] for c in result['recommendations']]
        self.assertEqual(len(topics), len(set(topics)))
        self.assertTrue(all('your interest' not in c['explanation'] for c in result['recommendations']))

    def test_obvious_interests_lead_the_list(self):
        first = recommend(self.db, 7)['recommendations'][:2]
        self.assertEqual({c['topic'] for c in first}, {'leadership-skills', 'public-speaking'})
        self.assertIn(6, [c['id'] for c in first])
        # #1 is a healthy leadership alternative to the planted #5.
        self.assertTrue(all('Matches your interest' in c['explanation'] for c in first))

    def test_negotiation_duplicates_are_limited(self):
        result = self.ids(15, 20)
        self.assertEqual(len(set(result) & {10, 11, 12}), 1)

    def test_full_and_inactive_alternative(self):
        result = self.ids(23)
        self.assertEqual(result[0], 22)
        self.assertNotIn(20, result)
        self.assertNotIn(21, result)
        # Isolate inactivity from #21's unlisted status.
        self.db.execute("UPDATE circles SET access='public' WHERE id=21")
        self.assertNotIn(21, self.ids(23, 20))

    def test_invariants_for_every_seed_user(self):
        for user in range(1, 101):
            with self.subTest(user=user):
                result = recommend(self.db, user, 20)['recommendations']
                self.assertTrue(result)
                self.assertLessEqual(len(result), 20)
                self.assertEqual(len({c['id'] for c in result}), len(result))
                joined = {r[0] for r in self.db.execute('SELECT circle_id FROM memberships WHERE user_id=?', (user,))}
                for c in result:
                    self.assertNotIn(c['id'], joined)
                    source = self.db.execute('SELECT * FROM circles WHERE id=?', (c['id'],)).fetchone()
                    self.assertEqual(source['access'], 'public')
                    self.assertTrue(source['max_members'] is None or source['member_count'] < source['max_members'])
                    self.assertTrue(c['explanation'])
                self.assertEqual([c['score'] for c in result], sorted([c['score'] for c in result], reverse=True))

    def test_no_candidates_is_valid_empty_list(self):
        self.db.execute("UPDATE circles SET access='unlisted'")
        self.assertEqual(self.ids(42), [])

    def test_capacity_boundary_and_uncapped(self):
        self.db.execute('UPDATE circles SET max_members=member_count WHERE id=1')
        self.assertNotIn(1, self.ids(42, 20))
        self.db.execute('UPDATE circles SET max_members=NULL WHERE id=1')
        self.assertIn(1, self.ids(42, 20))

    def test_no_future_or_stale_evidence(self):
        self.db.execute("UPDATE circles SET last_activity_at='2027-01-01T00:00:00Z' WHERE id=1")
        self.assertNotIn(1, self.ids(42, 20))
        self.assertEqual(recommend(self.db, 42, as_of='2027-09-21')['recommendations'], [])

    def test_inferred_interests_and_request_explanation(self):
        self.db.execute("INSERT INTO memberships VALUES (42,5,'member','2026-09-01T00:00:00Z')")
        self.db.execute("UPDATE circles SET join_policy='request'")
        result = recommend(self.db, 42)['recommendations']
        self.assertTrue(all('request to join' in c['explanation'] for c in result))
        self.assertTrue(any('already belong to' in c['explanation'] for c in result))

    def test_null_topics_and_duplicate_tags_load(self):
        self.assertGreater(self.db.execute('SELECT COUNT(*) FROM circles WHERE topic IS NULL').fetchone()[0], 0)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        seed(self.db)  # Re-seeding must not duplicate data.
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 100)

    def test_validation(self):
        with self.assertRaises(LookupError):
            recommend(self.db, 9999)
        for limit in [0, 21, -1, 2.5, True]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                recommend(self.db, 42, limit)


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create and use SQLite in the serving thread, just as the application does.
        cls.ready = threading.Event()
        def serve():
            db = connect()
            seed(db)
            cls.server = HTTPServer(('127.0.0.1', 0), make_handler(db, SNAPSHOT_DATE))
            cls.ready.set()
            cls.server.serve_forever()
            db.close()
        cls.thread = threading.Thread(target=serve)
        cls.thread.start()
        if not cls.ready.wait(5):
            raise RuntimeError('Test server did not start')

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def get(self, path):
        try:
            response = urlopen(f'http://127.0.0.1:{self.server.server_port}{path}', timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            self.assertIn('application/json', response.headers['Content-Type'])
            return response.status, json.load(response)

    def test_http_contract(self):
        for path, status in [('/health', 200), ('/users/42/recommendations', 200),
                             ('/users/7/recommendations?limit=2', 200),
                             ('/users/9999/recommendations', 404), ('/missing', 404),
                             ('/users/no/recommendations', 400), ('/users/0/recommendations', 400),
                             ('/users/7/recommendations?limit=0', 400),
                             ('/users/7/recommendations?limit=21', 400),
                             ('/users/7/recommendations?limit=abc', 400),
                             ('/users/7/recommendations?limit=', 400),
                             ('/users/7/recommendations?limit=2&limit=3', 400),
                             ('/users/7/recommendations?unknown=1', 400)]:
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], status)
        self.assertEqual(len(self.get('/users/7/recommendations?limit=2')[1]['recommendations']), 2)


if __name__ == '__main__':
    unittest.main()
