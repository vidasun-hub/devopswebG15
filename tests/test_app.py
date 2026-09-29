"""Run from the project folder with: python -m unittest discover -s tests -v."""

import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from html.parser import HTMLParser

from werkzeug.security import check_password_hash

from app import create_app
from stats import (
    MAX_ABSOLUTE_VALUE,
    MAX_INPUT_LENGTH,
    MAX_VALUES,
    calculate_statistics,
    parse_dataset,
)


class CSRFInputParser(HTMLParser):
    """Find a form token without depending on HTML attribute order."""

    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name") == "csrf_token":
            self.token = attributes.get("value")


class StatisticsTests(unittest.TestCase):
    def test_known_population_statistics(self):
        result = calculate_statistics([4, 1, 4, 2, 3])
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["sum"], 14)
        self.assertAlmostEqual(result["mean"], 2.8)
        self.assertEqual(result["median"], 3)
        self.assertEqual(result["mode"], [4])
        self.assertEqual(result["min"], 1)
        self.assertEqual(result["max"], 4)
        self.assertEqual(result["range"], 3)
        self.assertAlmostEqual(result["variance"], 1.36)
        self.assertAlmostEqual(result["standard_deviation"], math.sqrt(1.36))
        self.assertEqual(result["sorted"], [1, 2, 3, 4, 4])

    def test_mixed_separators_negative_decimal_and_scientific_values(self):
        values = parse_dataset("-2.5, +3\n.5\t1e1  -4E-1")
        self.assertEqual(values, [-2.5, 3, 0.5, 10, -0.4])
        result = calculate_statistics(values)
        self.assertAlmostEqual(result["sum"], 10.6)
        self.assertAlmostEqual(result["mean"], 2.12)
        self.assertEqual(result["median"], 0.5)
        self.assertEqual(result["mode"], [])

    def test_multiple_modes_and_even_median(self):
        result = calculate_statistics([3, 1, 3, 1, 2, 4])
        self.assertEqual(result["mode"], [1, 3])
        self.assertEqual(result["median"], 2.5)

    def test_unique_values_have_no_mode(self):
        self.assertEqual(calculate_statistics([1, 2, 3])["mode"], [])

    def test_singleton_has_zero_spread(self):
        result = calculate_statistics([-7])
        self.assertEqual(result["mode"], [-7])
        self.assertEqual(result["mean"], -7)
        self.assertEqual(result["median"], -7)
        for key in ("range", "variance", "standard_deviation"):
            self.assertEqual(result[key], 0)

    def test_constant_dataset_has_zero_spread(self):
        result = calculate_statistics([2.5, 2.5, 2.5])
        self.assertEqual(result["mode"], [2.5])
        self.assertEqual(result["variance"], 0)
        self.assertEqual(result["standard_deviation"], 0)

    def test_bad_or_nonfinite_values_are_rejected(self):
        for raw in ("", " \n\t", "1, apple, 3", "NaN", "Infinity", "-inf", "1e309", "2+3", "0x10"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_dataset(raw)

    def test_size_and_magnitude_limits(self):
        self.assertEqual(len(parse_dataset(" ".join(["1"] * MAX_VALUES))), MAX_VALUES)
        for raw in (
            " ".join(["1"] * (MAX_VALUES + 1)),
            "1" * (MAX_INPUT_LENGTH + 1),
            str(MAX_ABSOLUTE_VALUE * 10),
        ):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                parse_dataset(raw)

    def test_largest_accepted_values_keep_statistics_finite(self):
        values = parse_dataset(f"{-MAX_ABSOLUTE_VALUE}, {MAX_ABSOLUTE_VALUE}")
        result = calculate_statistics(values)
        for key in ("sum", "mean", "median", "range", "variance", "standard_deviation"):
            with self.subTest(statistic=key):
                self.assertTrue(math.isfinite(result[key]))


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        # Each test gets an independent database; the user's local data is untouched.
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.directory.name, "statistics.db")
        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.database_path,
            "SECRET_KEY": "test-secret-key-only",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.directory.cleanup()

    def rows(self, query, parameters=()):
        # sqlite3's own context manager commits a transaction but does not close
        # its file handle. Closing explicitly also permits cleanup on Windows.
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(query, parameters).fetchall()

    def token(self, path="/login", client=None):
        client = client or self.client
        response = client.get(path, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        parser = CSRFInputParser()
        parser.feed(response.get_data(as_text=True))
        self.assertTrue(parser.token, f"No CSRF form token on {path}")
        return parser.token

    def post(self, path, data=None, token_page="/login", client=None, follow=False):
        client = client or self.client
        form = dict(data or {})
        form["csrf_token"] = self.token(token_page, client)
        return client.post(path, data=form, follow_redirects=follow)

    def register(self, username="alice", email="alice@example.com", client=None):
        return self.post("/register", {
            "username": username,
            "email": email,
            "password": "correct-horse-123",
            "confirm_password": "correct-horse-123",
        }, token_page="/register", client=client)

    def login(self, identifier="alice", client=None):
        return self.post("/login", {
            "identifier": identifier,
            "password": "correct-horse-123",
        }, client=client)

    def authenticated(self):
        self.assertEqual(self.register().status_code, 302)
        self.assertEqual(self.login().status_code, 302)

    def calculate(self, dataset="10, 15, 20, 25, 30", client=None):
        return self.post("/calculate", {"dataset": dataset}, token_page="/dashboard", client=client)

    def test_database_is_created_with_foreign_key(self):
        self.assertTrue(os.path.isfile(self.database_path))
        tables = {row["name"] for row in self.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"users", "calculations"}.issubset(tables))
        foreign_keys = self.rows("PRAGMA foreign_key_list(calculations)")
        self.assertTrue(any(row["table"] == "users" and row["from"] == "user_id" for row in foreign_keys))

    def test_registration_hashes_password_and_rejects_duplicates(self):
        self.assertEqual(self.register().status_code, 302)
        users = self.rows("SELECT * FROM users")
        self.assertEqual(len(users), 1)
        self.assertNotEqual(users[0]["password_hash"], "correct-horse-123")
        self.assertTrue(check_password_hash(users[0]["password_hash"], "correct-horse-123"))
        self.register(email="another@example.com")
        self.register(username="different")
        self.assertEqual(len(self.rows("SELECT * FROM users")), 1)

    def test_registration_checks_password_confirmation(self):
        response = self.post("/register", {
            "username": "alice", "email": "alice@example.com",
            "password": "correct-horse-123", "confirm_password": "different-password",
        }, token_page="/register")
        self.assertIn(response.status_code, (200, 400))
        self.assertEqual(self.rows("SELECT * FROM users"), [])

    def test_login_accepts_email_and_wrong_password_does_not_authenticate(self):
        self.register()
        wrong = self.post("/login", {"identifier": "alice", "password": "incorrect-password"})
        self.assertIn(wrong.status_code, (200, 400, 401))
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        self.assertEqual(self.login("alice@example.com").status_code, 302)
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("alice", dashboard.get_data(as_text=True))

    def test_private_pages_require_login(self):
        for path in ("/dashboard", "/history", "/history/1", "/clear-history"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])

    def test_private_posts_require_login_even_with_valid_csrf(self):
        for path, form in (
            ("/calculate", {"dataset": "1 2 3"}),
            ("/delete-history/1", {}),
            ("/clear-history", {"confirm": "yes"}),
        ):
            with self.subTest(path=path):
                response = self.post(path, form)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])
        self.assertEqual(self.rows("SELECT * FROM calculations"), [])

    def test_csrf_is_required_for_registration_and_authenticated_actions(self):
        response = self.client.post("/register", data={
            "username": "alice", "email": "alice@example.com",
            "password": "correct-horse-123", "confirm_password": "correct-horse-123",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.rows("SELECT * FROM users"), [])
        self.authenticated()
        for path, form in (("/calculate", {"dataset": "1 2 3"}), ("/logout", {}), ("/clear-history", {"confirm": "yes"})):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, data=form).status_code, 400)
        self.assertEqual(self.client.post("/calculate", data={
            "dataset": "1 2 3", "csrf_token": "forged-token",
        }).status_code, 400)
        self.assertEqual(self.rows("SELECT * FROM calculations"), [])
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_calculation_saves_and_can_be_reopened(self):
        self.authenticated()
        response = self.calculate()
        self.assertEqual(response.status_code, 302)
        records = self.rows("SELECT * FROM calculations")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertAlmostEqual(record["mean"], 20)
        self.assertAlmostEqual(record["median"], 20)
        self.assertAlmostEqual(record["variance"], 50)
        self.assertAlmostEqual(record["standard_deviation"], math.sqrt(50))
        self.assertTrue(record["created_at"])
        self.assertEqual(self.client.get(f"/history/{record['id']}").status_code, 200)
        history = self.client.get("/history")
        self.assertEqual(history.status_code, 200)
        self.assertIn(f"/history/{record['id']}", history.get_data(as_text=True))
        # Reading a saved result or refreshing history must not insert another row.
        self.assertEqual(len(self.rows("SELECT * FROM calculations")), 1)

    def test_invalid_calculation_does_not_save_history(self):
        self.authenticated()
        for dataset in ("1, cat, 3", "", "NaN", "1e309"):
            with self.subTest(dataset=dataset):
                response = self.calculate(dataset)
                self.assertIn(response.status_code, (200, 302, 400))
        self.assertEqual(self.rows("SELECT * FROM calculations"), [])

    def test_users_cannot_view_or_delete_each_others_history(self):
        self.authenticated()
        self.calculate("987654, 987656")
        alice_record = self.rows("SELECT id FROM calculations")[0]["id"]
        bob = self.app.test_client()
        self.assertEqual(self.register("bob", "bob@example.com", bob).status_code, 302)
        self.assertEqual(self.login("bob", bob).status_code, 302)
        self.assertNotIn("987654", bob.get("/history").get_data(as_text=True))
        self.assertEqual(bob.get(f"/history/{alice_record}").status_code, 404)
        response = self.post(f"/delete-history/{alice_record}", token_page="/history", client=bob)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(self.rows("SELECT * FROM calculations")), 1)

    def test_clear_history_requires_confirmation_and_only_clears_current_user(self):
        self.authenticated()
        self.calculate("1 2 3")
        alice_record = self.rows("SELECT id FROM calculations")[0]["id"]
        bob = self.app.test_client()
        self.register("bob", "bob@example.com", bob)
        self.login("bob", bob)
        self.calculate("100 200", bob)
        self.assertEqual(len(self.rows("SELECT * FROM calculations")), 2)
        self.assertEqual(self.client.get("/clear-history").status_code, 200)
        self.post("/clear-history", token_page="/clear-history")
        self.assertEqual(len(self.rows("SELECT * FROM calculations")), 2)
        response = self.post("/clear-history", {"confirm": "yes"}, token_page="/clear-history")
        self.assertEqual(response.status_code, 302)
        remaining = self.rows("SELECT id FROM calculations")
        self.assertEqual(len(remaining), 1)
        self.assertNotEqual(remaining[0]["id"], alice_record)

    def test_delete_own_record_and_logout(self):
        self.authenticated()
        self.calculate()
        record_id = self.rows("SELECT id FROM calculations")[0]["id"]
        self.assertEqual(self.client.get(f"/delete-history/{record_id}").status_code, 405)
        deleted = self.post(f"/delete-history/{record_id}", token_page="/history")
        self.assertEqual(deleted.status_code, 302)
        self.assertEqual(self.rows("SELECT * FROM calculations"), [])
        self.assertEqual(self.client.get("/logout").status_code, 405)
        response = self.post("/logout", token_page="/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)


if __name__ == "__main__":
    unittest.main()
