# 🌐 Shodaner

### Automated Shodan OSINT Scanner — IoT Device Metadata Aggregator

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Selenium](https://img.shields.io/badge/Selenium-4.x-43B02A?style=for-the-badge&logo=selenium&logoColor=white)](https://www.selenium.dev/)
[![Shodan](https://img.shields.io/badge/Shodan-OSINT-1F72D9?style=for-the-badge)](https://www.shodan.io/)
[![License](https://img.shields.io/badge/License-MIT-000000?style=for-the-badge)](LICENSE)

**Passive intelligence-gathering automation for mapping IoT device footprints across geographic regions using Shodan's public search index.**

Built for security researchers, penetration testers, and network asset auditors who need structured, reproducible device metadata collection.

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [How It Works](#-how-it-works)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Output Format](#-output-format)
- [Search Modifiers](#-search-modifiers)
- [Chromium Profile](#-chromium-profile)
- [Troubleshooting](#-troubleshooting)
- [Pipeline Integration](#-pipeline-integration)
- [Legal](#-legal)

---

## 🔍 Overview

Shodaner automates the process of querying [Shodan](https://www.shodan.io/) — the world's largest search engine for internet-connected devices — and collects structured metadata about specific IoT device models across user-defined geographic regions.

Instead of manually searching each product/country combination through the web interface, Shodaner:

1. **Authenticates** into Shodan using your existing Google-linked account
2. **Iterates** through a configurable list of device products × countries
3. **Extracts** serial number patterns and indexing timestamps from result pages
4. **Deduplicates** entries by 4-character prefix to reduce noise
5. **Exports** everything to a clean `results.txt` file

### What Shodaner does:

| Capability | Description |
|:-----------|:------------|
| Multi-region scanning | Batch ISO country codes (RU, UA, US, DE, etc.) |
| Product filtering | Pre-configured list of Dahua IPC camera families |
| Serial extraction | Truncates to 10-character prefix for pattern analysis |
| Age calculation | Computes "days since last indexed" for each record |
| Auto-deduplication | Removes duplicate 4-character serial prefixes |
| Profile isolation | Clones Chrome profile to avoid corrupting daily-use data |

### What Shodaner does NOT do:

- ❌ Does not connect to any device
- ❌ Does not attempt authentication on devices
- ❌ Does not exploit vulnerabilities
- ❌ Does not interact with anything beyond Shodan's public web interface
- ✅ Only reads data already publicly indexed by Shodan

---

## ⚙️ How It Works

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   User Input     │       │   Chrome Clone   │       │   Shodan.io      │
│                  │       │                  │       │                  │
│  ISO Codes:      │──────▶│  Selenium takes  │──────▶│  Login via       │
│  "UA, KZ, RU"    │       │  control of a    │       │  Google OAuth    │
│                  │       │  cloned profile  │       │                  │
└──────────────────┘       └──────────────────┘       └────────┬─────────┘
                                                               │
                                                               ▼
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│   results.txt    │◀──────│  Parse & Filter  │◀──────│  Search Results  │
│                  │       │                  │       │                  │
│  Product [Date]  │       │  Regex extracts  │       │  Serial numbers  │
│  → Serial: XXXX  │       │  SN + timestamp  │       │  + timestamps    │
└──────────────────┘       └──────────────────┘       └──────────────────┘
```

**Automation pipeline:**

```
[1/7] Detect Chrome profile
[2/7] Clone profile (isolated sandbox)
[3/7] Launch Chrome (Selenium-controlled)
[4/7] Navigate to Shodan
[5/7] Authenticate via Google OAuth
[6/7] Execute search loop (product × country)
[7/7] Deduplicate prefixes → save results
```

---

## 📋 Requirements

| Component | Version | Purpose |
|:----------|:--------|:--------|
| Python | 3.8+ | Runtime |
| Google Chrome | latest | Selenium-compatible browser |
| ChromeDriver | matching | WebDriver automation layer |
| Shodan account | free tier | Access to search interface |
| Google account | — | OAuth login for Shodan |
| Internet | — | Stable connection recommended |

---

## 🔧 Installation

```bash
# Clone the repository
git clone https://github.com/therample/Shodaner.git
cd Shodaner

# Install Python dependencies
pip install -r requirements.txt
```

**requirements.txt:**
```
selenium>=4.10.0
```

> ⚠️ Ensure your ChromeDriver version matches your Chrome browser version. The tool will raise a descriptive error if there's a mismatch.

---

## ⚙️ Configuration

Open `shodaner.py` and locate the configuration block:

```python
# ─── Configuration ───

GOOGLE_EMAIL = "your_email@gmail.com"
GOOGLE_PASSWORD = "your_password"

BASE_PRODUCTS = [
    'product:"Dahua IPC-C15"',
    'product:"Dahua IPC-A35"',
    'product:"Dahua IPC-K15"',
    # ... add your own
]

TARGET_CODE_WORD = "Serial Number"
OUTPUT_FILE = "results.txt"
```

### Parameters

| Variable | Type | Description |
|:---------|:-----|:------------|
| `GOOGLE_EMAIL` | `str` | Google account email for Shodan OAuth |
| `GOOGLE_PASSWORD` | `str` | Google account password |
| `BASE_PRODUCTS` | `list[str]` | Shodan search queries (product filters) |
| `TARGET_CODE_WORD` | `str` | Keyword to extract from results (default: `"Serial Number"`) |
| `OUTPUT_FILE` | `str` | Output path (default: `results.txt`) |

### Adding Custom Products

Any valid [Shodan search filter](https://help.shodan.io/the-basics/search-query-fundamentals) works:

```python
BASE_PRODUCTS = [
    'product:"Dahua IPC-C15"',
    'product:"Hikvision DS-2CD"',
    'product:"Generic P2P Camera"',
    'port:37777',
    # Anything Shodan supports...
]
```

---

## 🚀 Usage

### Basic Run

```bash
python shodaner.py
```

The tool will prompt for ISO country codes interactively:

```
┌── Region Selection ──
│ Enter ISO codes separated by commas (e.g., UA, US, PL, DE)
└── ➔ RU, KZ, UA

[*] Target regions: [RU, KZ, UA]

[1/7] Detecting Chrome profile...
[2/7] Cloning profile to sandbox...
[3/7] Launching Chrome...
[4/7] Opening shodan.io...
[5/7] Authenticating via Google...
[6/7] Executing search queries...
[7/7] Deduplicating prefixes...
[+] All items processed (145.3s)
```

### Command-Line Arguments

```bash
python shodaner.py --help
```

| Flag | Default | Description |
|:-----|:--------|:------------|
| `--user-data-dir` | auto-detected | Chrome User Data directory path |
| `--profile-dir` | auto-detected | Chrome profile folder (e.g., `Default`, `Profile 1`) |
| `--verbose` | off | Show full stack traces on errors |

### Advanced Usage

```bash
# Use a specific Chrome profile
python shodaner.py --profile-dir "Profile 2"

# Use a custom Chrome installation
python shodaner.py --user-data-dir "D:\ChromeBackup\User Data"

# Debug mode with full tracebacks
python shodaner.py --verbose
```

---

## 📤 Output Format

Results are appended to `results.txt` in a structured, human-readable format:

```
product:"Dahua IPC-C15" country:"RU" [Date: 2024-01-15 | Age: today] -> Serial Number: ABCDEF1234
product:"Dahua IPC-A35" country:"UA" [Date: 2024-01-14 | Age: yesterday] -> Serial Number: F1E2D3A456
product:"Dahua IPC-K15" country:"KZ" [Date: 2024-01-10 | Age: 5 days ago] -> Serial Number: 123456A789
```

### Fields

| Field | Source | Description |
|:------|:-------|:------------|
| Product query | input | Original Shodan search string |
| Country | ISO code | Region where device was indexed |
| Date | Shodan | When the record was last updated |
| Age | calculated | Human-readable time since indexing |
| Serial Number | extracted | First 10 characters of the SN |

### Age Labels

| Label | Meaning |
|:------|:--------|
| `today` | Indexed within the current day |
| `yesterday` | Indexed 1 day ago |
| `N days ago` | Indexed N days ago |

> 💡 **Tip:** Freshly indexed records (today/yesterday) are more likely to reflect currently active devices.

---

## 🌍 Search Modifiers

Shodaner builds search queries by combining `BASE_PRODUCTS` with country filters:

```
product:"Dahua IPC-C15" country:"RU"
product:"Dahua IPC-C15" country:"UA"
product:"Dahua IPC-C15" country:"KZ"
product:"Dahua IPC-A35" country:"RU"
...
```

If you enter **3 regions** and have **11 products**, the tool executes **33 searches** sequentially.

### Supported ISO 3166-1 alpha-2 Codes

<details>
<summary><b>📋 Expand to see popular codes</b></summary>

| Code | Country | Code | Country | Code | Country |
|:----:|:--------|:----:|:--------|:----:|:--------|
| RU | Russia | US | United States | CN | China |
| UA | Ukraine | KZ | Kazakhstan | DE | Germany |
| FR | France | GB | United Kingdom | BR | Brazil |
| IN | India | TR | Turkey | ID | Indonesia |
| TH | Thailand | VN | Vietnam | MX | Mexico |
| AR | Argentina | PL | Poland | IT | Italy |
| ES | Spain | NL | Netherlands | BY | Belarus |

Full reference: [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)

</details>

---

## 🧬 Chromium Profile

Shodaner clones your Chrome profile into an isolated temporary directory before launching. This means:

- ✅ Your daily-use Chrome profile stays untouched
- ✅ No conflicts with concurrently running Chrome instances
- ✅ Bookmarks, history, and extensions are preserved in the clone
- ✅ Heavy directories (caches, extensions, GPU data) are excluded for speed

### Excluded Directories (Optimization)

The following directories are skipped during cloning to reduce copy time:

```
Cache, Code Cache, GPUCache, Service Worker, blob_storage,
IndexedDB, Local Storage, Session Storage, GrShaderCache,
ShaderCache, DawnCache, Media Cache, Extensions, Crashpad, ...
```

---

## 🐛 Troubleshooting

<details>
<summary><b>Chrome won't launch</b></summary>

```
[x] Failed to launch managed Chrome.
```

**Solutions:**
1. Verify ChromeDriver version matches your Chrome version
2. Check if antivirus/EDR is blocking Selenium
3. Ensure write permissions on temp directory
4. Run with `--verbose` for full error details

</details>

<details>
<summary><b>Login not working</b></summary>

```
[x] Didn't find Google button — waiting, maybe you can click manually...
```

**Solutions:**
1. Shodan may have changed their login UI — click manually
2. Clear Shodan cookies and retry
3. Verify your Google account doesn't have 2FA prompts blocking automation
4. Check if your account is locked/suspended

</details>

<details>
<summary><b>Pages loading slowly / hanging</b></summary>

**Cause:** OS reduces Chrome priority when the window is minimized.

**Solutions:**
1. Keep both the terminal and Chrome window in the foreground
2. Don't run bandwidth-heavy tasks simultaneously (downloads, streams)
3. Reduce the number of simultaneous countries
4. Check your internet connection stability

</details>

<details>
<summary><b>No results found</b></summary>

```
[x] Nothing found on the results page for '...'
```

**Possible causes:**
1. No matching devices in the selected country
2. Shodan hasn't indexed devices with that product in that region recently
3. The product name in `BASE_PRODUCTS` is misspelled

**Try:** Verifying your query manually on shodan.io first

</details>

<details>
<summary><b>Zombie Chrome processes after exit</b></summary>

Shodaner automatically executes `taskkill` (Windows) or `pkill` (Linux/Mac) on exit. If processes persist:

```bash
# Windows
taskkill /F /T /IM chrome.exe
taskkill /F /T /IM chromedriver.exe

# Linux / macOS
pkill -f chromedriver
pkill -f chrome
```

</details>

---

## 🔗 Pipeline Integration

Shodaner is designed as **Stage 1** of a three-stage research pipeline:

| Stage | Tool | Input | Output |
|:------|:-----|:------|:-------|
| 1️⃣ | **Shodaner** | ISO codes | `results.txt` (prefixes) |
| 2️⃣ | [Krushitel](https://github.com/undervolter/krushitel) | `results.txt` | Validated serial numbers |
| 3️⃣ | [P2PWN](https://github.com/thebadinteger/p2pwn) | Validated SNs | Audit reports (XML) |

---

## ⚠️ Operational Notes

1. **Do not minimize** the terminal or Chrome window during operation
2. **Do not run** other bandwidth-heavy applications concurrently
3. **Scan duration** scales linearly: more regions = more time
4. **Free Shodan accounts** may encounter rate limits — the tool handles retries automatically
5. **Google 2FA** may require manual intervention on first login
6. **Window size** is set to 800×600 for optimal Shodan rendering

---

## 🤝 Contributing

```bash
# Fork → Branch → Commit → Push → Pull Request
git checkout -b feature/new-capability
git commit -m "Add: new capability"
git push origin feature/new-capability
```

### Ideas for Contributions

- [ ] Headless mode (`--headless` flag)
- [ ] API-based mode (bypass Selenium using Shodan API key)
- [ ] Custom output formats (CSV, JSON, XML)
- [ ] Rate limiting configuration
- [ ] Proxy support
- [ ] Docker containerization

---

## 📜 License

```
MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## ⚖️ Legal & Ethics

This tool accesses **only publicly available data** indexed by Shodan. It does not interact with, connect to, or authenticate against any device.

Users are responsible for:

- Compliance with their local laws and regulations
- Compliance with Shodan's Terms of Service
- Compliance with Google's Terms of Service
- Ethical use of collected data

**Intended for:** authorized security research, penetration testing, academic study, and network asset management.

**Not intended for:** unauthorized access, harassment, stalking, or any activity that violates laws in your jurisdiction.
