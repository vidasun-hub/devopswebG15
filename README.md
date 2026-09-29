# Basic Statistics Calculator

A complete, small Flask application for registering an account, calculating descriptive statistics, and keeping your own calculation history. The frontend uses HTML, CSS, and vanilla JavaScript. SQLite stores accounts and saved results; no separate database server is needed.

## Run on Windows

Install Python if it is not already available, then open a terminal in the `basic_statistics` folder. You can check the installation with `python --version`. If Windows recognizes `py` instead of `python`, use `py` for the command that creates the virtual environment.

Choose the instructions for your terminal. The `cd` commands below use the location where this project was created; change that location if you move the folder.

### Command Prompt (CMD)

```bat
cd /d C:\Users\amar\Documents\ChatGPT\web\basic_statistics
python -m venv venv
venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python app.py
```

### PowerShell

```powershell
Set-Location 'C:\Users\amar\Documents\ChatGPT\web\basic_statistics'
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

If PowerShell blocks the activation script, you can run the virtual environment's Python directly without changing any execution policy:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000** in your browser. Keep the terminal open while using the website. Stop the server with **Ctrl+C**. On later visits, activate the existing virtual environment and run `python app.py`; you only need to create the environment and install dependencies once.

The application creates `statistics.db` automatically alongside `app.py` on its first start. Do not create or download a blank database yourself. There is no demo account: select **Create account**, register, and log in.

Only Flask and its small Python dependencies are installed. SQLite, the calculation helpers, and the test runner use Python's standard library. There is no Node.js installation, frontend build step, CDN, or separate API server.

## Using the calculator

1. Register with a unique username and email. Usernames use 3–30 letters, numbers, or underscores; passwords use 8–128 characters.
2. Log in with your username or email and password.
3. Enter numbers separated by commas, spaces, tabs, or new lines, then select **Calculate**.
4. Read the ten result cards, formulas, and sorted dataset. Every successful calculation is saved to your account.
5. Open **Calculation History** to view an earlier result, delete a record, or clear your history. Clearing all records requires a confirmation page.
6. Use **Logout** to end the current session.

Example input:

```text
10, 15, 20, 25, 30
```

This produces count **5**, sum **100**, mean **20**, median **20**, no mode, minimum **10**, maximum **30**, range **20**, population variance **50**, and population standard deviation approximately **7.071068**.

Negative numbers, decimals, and scientific notation work too:

```text
-2.5 3
0.5, 1e1, -4E-1
```

Use a period for the decimal point. Commas separate values, so enter one thousand as `1000`, not `1,000`. Blank input, words, expressions such as `2+3`, infinity, and `NaN` are rejected. One calculation accepts up to **10,000 values**, **200,000 input characters**, and an absolute value of **1e100** per number. Limits are checked in Python even when browser validation is disabled.

The input **Clear** button clears the current dataset entry; it does not delete saved history. Viewing a saved result and refreshing the page do not save duplicate records. Calculating that dataset again intentionally creates a new history entry.

## Project structure

```text
basic_statistics/
├── app.py                 # Flask routes, sessions, authentication, and CSRF
├── database.py            # SQLite connection management and schema
├── stats.py               # Parsing, statistics, and number formatting
├── requirements.txt       # Python dependency specification
├── README.md
├── .gitignore
├── statistics.db          # Generated automatically when the app starts
├── templates/
│   ├── base.html          # Shared navigation, messages, and page layout
│   ├── _icons.html        # Reusable inline SVG icons
│   ├── _auth_intro.html   # Shared introduction on login and registration
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── history.html
│   ├── clear_history.html # Confirmation before clearing all history
│   └── error.html
├── static/
│   ├── favicon.svg
│   ├── css/style.css
│   └── js/script.js
└── tests/
    └── test_app.py
```

The `venv` directory and Python cache directories appear locally after installation and running the project. They are generated files, not application source.

## How a request works

Flask receives a browser request and selects a route in `app.py`. Routes read or write SQLite through `database.py`, then render a Jinja HTML template. CSS styles the page, and JavaScript improves validation and interaction. The browser submits ordinary HTML forms, so the main registration, login, calculation, and history flows also work without JavaScript.

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | Send visitors to login or their dashboard |
| `/register` | GET, POST | Show the registration form and create an account |
| `/login` | GET, POST | Show the login form and authenticate |
| `/dashboard` | GET | Show the calculator and recent history |
| `/calculate` | POST | Validate, calculate, save, and redirect to the saved result |
| `/history` | GET | List the current user's calculations |
| `/history/<id>` | GET | Open a calculation belonging to the current user |
| `/delete-history/<id>` | POST | Delete one calculation belonging to the current user |
| `/clear-history` | GET, POST | Show confirmation, then clear the current user's history |
| `/logout` | POST | Clear the login session |

Successful form submissions redirect to another page. In particular, `/calculate` redirects to `/history/<id>` after saving, so refreshing the result does not submit the form again.

## Database structure

`database.py` creates two tables with `CREATE TABLE IF NOT EXISTS`.

| Table | Columns |
| --- | --- |
| `users` | `id`, `username`, `email`, `password_hash`, `created_at` |
| `calculations` | `id`, `user_id`, `dataset`, `count`, `total`, `mean`, `median`, `mode`, `minimum`, `maximum`, `value_range`, `variance`, `standard_deviation`, `created_at` |

Usernames and emails are unique without regard to letter case. `calculations.user_id` is a foreign key pointing to `users.id`; foreign-key checks are enabled on every application connection. The schema also includes an index for looking up each user's calculations in date order.

`dataset` stores the original sequence of parsed numbers as JSON text. It preserves number order, but not the original spaces or exact decimal spelling. `mode` is another JSON list because a dataset can have several modes. An empty list means “No mode.” Numerical results use SQLite `REAL` columns, and count uses an integer. `total` stores the sum, and `value_range` stores the range. Dates are recorded in UTC; JavaScript displays them in your browser's local timezone. With JavaScript disabled, dates remain labeled as UTC.

SQLite uses a local file and has no database username or password to configure. To back up your data, stop the app and copy `statistics.db` somewhere private. Anyone who can read that file can read stored datasets and account metadata. Account isolation is enforced by the website; the database file itself is not encrypted. The generated database is excluded from version control.

## Login and security

Registration checks the form on the server and uses Werkzeug's `generate_password_hash()` to store a salted password hash. Login checks the supplied password with `check_password_hash()`. Plain passwords are never written to SQLite.

After successful login, Flask clears the previous session and stores the user's ID in its signed session cookie. The secret key prevents a visitor from modifying that cookie undetected; the cookie is signed, not encrypted. Dataset contents and password hashes are not stored in the session. Each private route checks authentication, and every history lookup or deletion also includes the current user's ID in its SQL query. A record belonging to someone else returns a 404 response.

SQL queries use parameters instead of constructing SQL from user input. Jinja escapes user-provided text in HTML. Every POST form includes a random CSRF token that the server verifies. Deleting records, clearing history, and logging out use POST requests. Session cookies use `HttpOnly` and `SameSite=Lax`, and private page responses disable caching.

### Secret key configuration

For simple local development, the app creates a random secret key once per Python process when `SECRET_KEY` is absent. No setup is required, but restarting the server signs existing users out. After a restart, refresh an old form before submitting it so that it receives a new CSRF token.

To keep a key across server restarts from the same PowerShell terminal, set it before starting the app:

```powershell
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Generate this value once per terminal session, then reuse it while restarting `python app.py`. For persistent or public deployment, configure a strong, private `SECRET_KEY` in the server's environment and keep the same value between restarts. Do not put real secret keys in source files or commit them to Git.

The local development server binds to `127.0.0.1:5000` with debug mode disabled. A public deployment needs a production WSGI server and HTTPS. With HTTPS, set `SESSION_COOKIE_SECURE=true` so browsers send session cookies only over secure connections. Leave that variable unset for the local HTTP address. This student project does not include password reset, email verification, or login rate limiting.

## How statistics are calculated

`parse_dataset()` splits comma and whitespace separators, validates the numeric format, and converts values to Python floats. `calculate_statistics()` then uses Python's `statistics`, `math`, and `collections.Counter` modules. No statistical service or third-party math package is needed.

For values `x₁, x₂, …, xₙ`, with mean `μ`:

| Statistic | Calculation |
| --- | --- |
| Count | `n`, the number of values |
| Sum | `Σxᵢ` |
| Mean | `μ = Σxᵢ / n` |
| Median | Middle sorted value, or the average of the two middle values |
| Mode | All values tied for the highest repeated frequency |
| Minimum / maximum | First / last value in the sorted sequence |
| Range | `maximum − minimum` |
| Population variance | `σ² = Σ(xᵢ − μ)² / n` |
| Population standard deviation | `σ = √σ²` |

The calculator treats the entered values as the entire **population**, so variance divides by `n`. Sample variance would divide by `n − 1`; it is not the quantity shown here. A single-value dataset has zero variance and standard deviation.

Mode conventions are explicit: `[1, 2, 3]` has no mode; `[1, 1, 2, 2, 3]` has modes `1, 2`; a single value is its own mode. The mode list is sorted numerically.

Cards display up to six decimal places, removing unnecessary trailing zeros. Very large numbers (absolute value at least `1e12`) and very small nonzero numbers (below `1e-6`) use scientific notation. This formatting affects display only. Calculations and saved values use floating-point precision, so tiny rounding differences are possible; this is not an arbitrary-precision decimal calculator.

## Changing the appearance and behavior

Edit `static/css/style.css`. The `:root` block near the beginning holds CSS variables for important design values: `--accent` sets the main color, `--page` and `--surface` control backgrounds, `--ink` and `--muted` control text, and `--radius`, `--shadow`, `--max-width`, and `--font` control shape and sizing. The remaining sections style navigation, forms, result cards, history, and responsive layouts. Media queries near the end adapt the layout for smaller screens.

Edit the templates to change page text and layout. `base.html` is shared by the other pages, so navigation changes belong there. Edit `static/js/script.js` for browser validation, clearing the input, and confirmation interactions. Keep the corresponding Python checks in `app.py` and `stats.py`: JavaScript improves feedback, but the server decides what can be saved.

For a calculation change, start in `stats.py`, then update any formula text in the templates and the relevant tests. Input limits are enforced in Python and JavaScript; keep both versions consistent when changing them. After updating CSS or JavaScript, refresh the browser with **Ctrl+F5** if it still shows the older version.

## Run the tests

From the project folder, with the virtual environment activated:

```bat
python -m unittest discover -s tests -v
```

Without activating the environment, PowerShell can run:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover known statistical results, mixed input formats, negative and scientific values, multimodal and singleton datasets, invalid values and limits, password hashing, authentication, CSRF, database creation, calculation persistence, and isolation between two users' history. Each application test uses a temporary database, so it does not change your own `statistics.db`.

For a manual check, register two accounts and verify that each sees only its own history. Try comma-, space-, and newline-separated input, an invalid word, the input Clear button, a saved calculation, record deletion, clear-all cancellation and confirmation, and logout. Resize the browser to check the mobile layout.

## Troubleshooting

- **`python` is not recognized:** try `py` to create the virtual environment, or install Python with its PATH option enabled.
- **`No module named flask`:** install requirements using the same Python that runs the app. The direct `venv\Scripts\python.exe` commands above avoid environment confusion.
- **Port 5000 is already in use:** stop another copy of the app with Ctrl+C. Alternatively, choose another port in the final `run()` call in `app.py` and open that port in your browser.
- **A form expired:** refresh the page and submit it again. This can happen after restarting the server when using the temporary development secret.
- **Changes do not appear:** restart the server after Python changes and use Ctrl+F5 after CSS or JavaScript changes. Debug and automatic reload are disabled by default.
- **Database cannot be written:** keep the project in a folder your Windows account can write to, and close any database tool holding an exclusive lock.

To learn more about the framework patterns used here, see Flask's official [session introduction](https://flask.palletsprojects.com/en/stable/quickstart/#sessions) and [SQLite connection pattern](https://flask.palletsprojects.com/en/stable/patterns/sqlite3/).
