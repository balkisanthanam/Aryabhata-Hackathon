# JEE Main Answer Key — 3rd Party Site Evaluation Report

**Date:** 2026-03-19
**Branch:** feature/jeeascent
**Purpose:** Evaluate 3rd party education sites as supplementary sources for JEE Main answer keys, given that our NTA download pipeline (`download_answer_keys.py`) ingested non-answer PDFs alongside actual answer keys, leaving the answer corpus unreliable.

---

## Context: Why We Need This Evaluation

Our existing `download_answer_keys.py` pipeline scrapes `jeemain.nta.nic.in/document-category/archive/`. The NTA archive page contains a mix of content categories — answer keys, question papers, notices, and other documents — with overlapping or ambiguous titles. Our `classify_title()` filter was not precise enough, resulting in non-answer-key PDFs being downloaded and stored in `exam_answer_keys`. After filtering these out we will have fewer confirmed answer keys than expected.

**This is why** we are evaluating 3rd party sites: to see if they can fill the gaps with per-question answer data that is linked (or linkable) to NTA Question IDs — the join key used by `jee_answer_mappings` and the entire Module 1b extraction pipeline.

---

## 1. Embibe (`embibe.com`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Guide/news articles** — directs users to NTA's official portal |
| Free without login? | Browsing is free; downloading requires NTA portal credentials (application number + DOB) |
| Per-question structured data? | **No** — PDF downloads only; no HTML table or JSON |
| Years/sessions available | 2022–2025 confirmed on page |
| robots.txt scraping restriction | `/exams/*` is **allowed**; `/*.pdf$` is **disallowed** |
| Data format | Links to NTA portal (jeemain.nta.nic.in) — no self-hosted PDFs |
| NTA Question IDs shown? | **No** |

**Notes:** Embibe is primarily a test-prep and analytics platform, not an answer key archive. Their answer key pages are article guides that walk candidates through the NTA official portal download process. They do not host the PDF content themselves. The actual download redirects to the NTA government CDN. Embibe may have a proprietary structured question bank behind their app login (used for their test engine), but this is not publicly accessible.

**Verdict for AryaBhatta:** ❌ Not a viable source. Embibe is a news/guide site acting as a wrapper around the same NTA source we already use. No self-hosted content, no NTA IDs on public pages.

---

## 2. Careers360 (`engineering.careers360.com`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Guide/news articles** — references official NTA answer keys; directs to NTA portal |
| Free without login? | Article pages are free; downloads may link to NTA portal |
| Per-question structured data? | **No** — PDF format only |
| Years/sessions available | **2016–2025** (question papers page); recent answer key articles up to 2026 Session 1 |
| robots.txt scraping restriction | **`Disallow: /*.pdf$`** — PDF files explicitly blocked from crawling |
| Data format | PDFs (likely NTA CDN links); article HTML |
| NTA Question IDs shown? | **No** |

**Notes:** Careers360 is a large education news and guidance portal. Their JEE answer key articles follow the same pattern as Embibe — informational guides pointing to the NTA official portal. Coverage is broad (2016–2025) but all content is PDF-based with no per-question structured data. Notably, their robots.txt explicitly disallows crawling of PDF files, which would be the primary content of interest. The articles themselves are freely browsable HTML but contain no answer data directly.

**Verdict for AryaBhatta:** ❌ Not a viable source. Same NTA-redirect pattern as Embibe; robots.txt blocks PDF crawling; no NTA IDs or per-question data.

---

## 3. Resonance (`resonance.ac.in`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Resonance-generated** — independently prepared by Resonance faculty; explicitly attributed to "Resonance Kota" |
| Free without login? | Partially — 2023 and 2024 PDFs accessible at predictable URLs without auth; page shows a registration form but it is a soft marketing gate only |
| Per-question structured data? | **No** — image-based PDFs (JPEG-embedded, not text-searchable) |
| Years/sessions available | **2013–2026** (index claims 13 years); 2019, 2021, 2023 sessions confirmed in detail |
| robots.txt scraping restriction | `/answer-key-solutions/` path **not blocked**; only internal admin paths restricted |
| Data format | Subject-wise PDFs per shift; predictable URL pattern: `resonance.ac.in/answer-key-solutions/JEE-Main/{year}/Solutions/CBT/{DD-MM-YYYY}/Shift-{1\|2}/{subject}.pdf` |
| NTA Question IDs shown? | **No** — uses Resonance's own sequential numbering (Q.01–Q.20) |

**Session detail (2023 confirmed):**
- April Session: Apr 06, 08, 10, 11, 12, 13, 15 × Shift 1 + Shift 2
- January Session: Jan 24, 25, 29, 30, 31 + Feb 01 × Shift 1 + Shift 2

**Notes:** Resonance is the most technically accessible of the coaching institutes surveyed. PDFs at predictable, unauthenticated URLs for at least 2019–2024. However, the content is **memory-based reconstructions** — faculty reconstruct questions from student recall after CBT exams. They use their own Q.01–Q.20 numbering, which is incompatible with NTA's numeric Question IDs required by `jee_answer_mappings`. The ToS page returned a 404, so scraping restrictions are unknown. For recent exams (2025+), a full enrollment form is shown (though PDFs may still be guessable).

**Verdict for AryaBhatta:** ⚠️ Accessible but not linkable. PDFs are freely downloadable at predictable URLs with broad year coverage, but the absence of NTA Question IDs makes them incompatible with our answer-key linkage mechanism without a separate question-matching step. Possible use for Tier 2 step-up problems if question text can be extracted via OCR.

---

## 4. Allen (`allen.ac.in`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Allen-generated** (coaching institute solutions) |
| Free without login? | **No** — primary delivery is through e-store (paid books) and enrolled student portal |
| Per-question structured data? | **No** — sold as physical/digital books; no free online structured data |
| Years/sessions available | 2025–2026 on homepage; archive availability unknown (requires login) |
| robots.txt scraping restriction | Not assessed (homepage had no answer key content to evaluate further) |
| Data format | Physical books (sold via Amazon/Flipkart), online test series behind login |
| NTA Question IDs shown? | **No** |

**Notes:** Allen's business model is fundamentally different from Resonance — they monetise their study materials. The homepage promotes their e-store and enrolled-student portal. Unlike Resonance, there is no free public archive of past answer key PDFs. Any historical JEE Main solutions appear to be gated behind either a purchase or student enrollment. Allen is not a viable free data source.

**Verdict for AryaBhatta:** ❌ Not a viable source. Content is behind a paywall. Not a free open archive.

---

## 5. Physics Wallah / PW (`pw.live`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Both** — clearly distinguished: (a) official NTA links pointing to `cdnbbsr.s3waas.gov.in`; (b) PW unofficial keys prepared from "memory-based questions" |
| Free without login? | **Yes** — article pages and PDF links freely accessible, no login required |
| Per-question structured data? | **No** — PDF downloads only; article pages have only a status table (not per-question data) |
| Years/sessions available | 2026 Session 1 confirmed; claims 2019–2025 archive on previous-year-papers page |
| robots.txt scraping restriction | `/iit-jee/exams/` path **not blocked** — answer key pages are crawlable |
| Data format | PDF links; official keys link to NTA CDN (`cdnbbsr.s3waas.gov.in`); unofficial keys on `static.pw.live` |
| NTA Question IDs shown? | Only in official NTA PDFs (which PW links to but does not host); unofficial memory-based PDFs have **no NTA IDs** |

**Notes:** PW acts as a dual publisher: (1) an informational guide pointing to the same NTA CDN we already access, and (2) a publisher of their own unofficial memory-based answer keys hosted on `static.pw.live`. The official NTA links offer no value over going directly to NTA. The unofficial PW PDFs are incompatible with our schema (no NTA IDs). ToS contains broad IP ownership language that would make using their unofficial PDF content in a commercial product legally problematic.

**Verdict for AryaBhatta:** ❌ Not a viable source. Official NTA links are redundant (same CDN we use). Unofficial keys have no NTA IDs and ToS prohibits commercial use of content.

---

## 6. Drishti JEE (`drishtijee.com`)

| Criterion | Finding |
|-----------|---------|
| Exists? | **No** — parked GoDaddy domain |
| All other criteria | N/A |

**Verdict for AryaBhatta:** ❌ Does not exist. Remove from candidate list.

---

## 7. Shaalaa (`shaalaa.com`)

| Criterion | Finding |
|-----------|---------|
| Official NTA keys or site-generated? | **Site-generated reproductions** — digitized NTA papers inside Shaalaa's own test engine; not official NTA PDFs |
| Free without login? | Test listing page is free; **actual answers require login** |
| Per-question structured data? | Yes (inside login-gated test engine) — questions rendered one at a time in HTML with MathJax; answers revealed after test completion |
| Years/sessions available | **2019–2022 only** — 8 papers per subject; nothing for 2023–2025 |
| robots.txt scraping restriction | Blocks GPTBot explicitly; ToS **explicitly prohibits scraping**: *"Use deep-links, page-scrape, robot, spider or other automatic device..."* |
| Data format | Interactive HTML test engine (login required for answers); no PDFs |
| NTA Question IDs shown? | **No** — Shaalaa uses sequential position numbers (Q1–Q90); NTA IDs absent |

**Verdict for AryaBhatta:** ❌ Not a viable source. ToS explicitly prohibits scraping. Answers are login-gated. No NTA Question IDs. Coverage only 2019–2022.

---

## Recommendation Table

| Site | Free Access | NTA Official PDFs | NTA Question IDs | Per-Question Data | Scraping OK | Coverage | Overall |
|------|-------------|-------------------|------------------|-------------------|-------------|----------|---------|
| Embibe | Partial | Links only (→ NTA) | No | No | Partial¹ | 2022–2025 | ❌ |
| Careers360 | Yes | Links only (→ NTA) | No | No | ⚠️ PDFs blocked² | 2016–2025 | ❌ |
| Resonance | Partial³ | No (own keys) | **No** | No | Likely OK | 2013–2026 | ⚠️ |
| Allen | **No** (paid) | No (own keys) | No | No | No | 2025–2026 | ❌ |
| Physics Wallah | Yes | Links only (→ NTA) | No | No | ⚠️ ToS risk | 2019–2026 | ❌ |
| Drishti JEE | — | — | — | — | — | — | ❌ (no site) |
| Shaalaa | Partial⁴ | No (own engine) | **No** | Behind login | **Prohibited** | 2019–2022 | ❌ |

**Footnotes:**
1. Embibe robots.txt blocks `/*.pdf$` but allows `/exams/*` article pages
2. Careers360 robots.txt `Disallow: /*.pdf$`
3. Resonance PDFs at predictable unauthenticated URLs for 2019–2024; 2025+ may require enrollment form
4. Shaalaa test listing is free; answers require login

---

## Key Finding: No 3rd Party Site Provides NTA Question IDs

**This is the critical blocker.** Every 3rd party site surveyed — coaching institutes (Resonance, Allen, PW unofficial) and content platforms (Shaalaa) — uses its own question numbering. None expose the NTA's internal numeric Question IDs that appear in the official answer key PDFs and serve as the join key in `jee_answer_mappings`.

The only source of NTA Question IDs is the NTA's own official answer key PDFs from `jeemain.nta.nic.in`. 3rd party sites cannot substitute for or supplement NTA official answer keys for the purpose of populating `jee_answer_mappings`.

---

## Architecture Conflicts Flagged

### Conflict 1: Module 1b — Answer Key Cross-Reference Assumption
**Architecture doc states (Module 1b, Step 4):**
> *"Answer key cross-reference — Parse answer key PDF (separate file); map NTA Question ID → Correct Option ID → answer text"*

**Reality:** This step implicitly assumes we have reliable NTA official answer key PDFs with NTA Question IDs. The data quality problem (non-answer PDFs mixed into `exam_answer_keys`) undermines this step. 3rd party sites cannot fill this gap because they lack NTA IDs.

**Resolution needed:** Fix the classification problem in `download_answer_keys.py` / `classify_title()` rather than seeking 3rd party substitutes. The NTA official site remains the only valid source.

### Conflict 2: Module 1c — Step-Up Problems from Coaching Institutes
**Architecture doc states (Module 1c):**
> *"Coaching institute open question banks (scrape where permitted)"*
> *Sources listed: Resonance, Allen*

**Reality:**
- **Allen** is not a free open bank — materials are behind paywall/login
- **Resonance** has freely accessible PDFs (no explicit ToS restriction found) but they are image-based (not text-searchable) and use memory-based reconstruction for recent years. Extracting questions via OCR is feasible but adds significant pipeline complexity. These would be suitable only for Tier 2 step-up problems, not answer key linkage.
- Neither site provides NTA Question IDs, which means scraped questions cannot be cross-referenced with NTA answer keys

**Resolution needed:** Update Module 1c to clarify that coaching institute content is viable only for Tier 2 step-up problems (where NTA ID linkage is not required) and only through OCR-based extraction. Resonance is the only viable coaching institute source for free public content.

### Conflict 3: Sources Priority Order in Module 1b
**Architecture doc lists as Source #4:**
> *"Coaching institute open question banks (Resonance, Allen)"*

This appears in Module 1b (JEE Main Past Papers extraction), which requires NTA Question IDs for answer key cross-referencing. **Coaching institute content is incompatible with Module 1b** because it lacks NTA IDs. This source should be removed from Module 1b and scoped only to Module 1c (Step-up problems).

---

## Recommended Action Plan

1. **Primary fix (answer key gap):** Improve `classify_title()` in `download_answer_keys.py` to more precisely filter NTA archive PDFs. Examine the mistakenly-downloaded PDFs to understand what patterns slipped through. The NTA archive is the only valid source for NTA-ID-linked answer keys.

2. **Secondary option (coverage gaps):** For exam sessions where NTA answer key PDFs cannot be recovered, consider parsing NTA question papers to extract NTA Question IDs directly (they appear in the paper alongside each question), then cross-referencing with any available answer signal. This avoids dependence on the separate answer key PDF entirely.

3. **Resonance for Tier 2 only:** Resonance is the only viable 3rd party source for free historical content (2013–2024), but only for Tier 2 step-up problems. Extraction requires OCR (image-based PDFs). This should be a separate pipeline, not part of Module 1b.

4. **Drop from architecture:** Remove Allen, Embibe, Careers360, PW, Shaalaa, and Drishti JEE from the data source list. None provide value beyond what the NTA official pipeline already gives us.

---

*Report generated from live Playwright/WebFetch investigation of all 7 candidate sites on 2026-03-19.*

---

## Approach 8: Google-Driven NTA PDF Discovery

**Date:** 2026-03-20
**Branch:** feature/jeeascent
**Purpose:** Evaluate whether Google search can surface official NTA answer key PDFs directly for specific JEE Main exam dates and shifts, bypassing the `jeemain.nta.nic.in/document-category/archive/` listing approach.

---

### Method

8 sample question papers were read via PyMuPDF to extract exam date and shift. Google searches were run via Playwright for each, testing two search string formats. Where a direct NTA PDF link appeared, the PDF was downloaded and page 1 was inspected for NTA Question IDs.

---

### NTA Question ID Format by Year

A key finding is that the Question ID digit count varies across years. The extraction pipeline must handle all formats:

| Year | Question ID digits | Correct Option ID (MCQ) | Example Question ID |
|------|--------------------|-------------------------|---------------------|
| 2021 | 10-digit | 11-digit | `8643513511` |
| 2022 | 11-digit | 12-digit | `15477154521` |
| 2023 | 10-digit | 11-digit | `7155053682` |
| 2024 | 11-digit | 12-digit | `87827056148` |

Integer-type questions use raw numeric answers (e.g., `18`, `420`) across all years.

---

### Answer Key PDF Structure (All Years)

- One PDF per session covers **all exam dates and all shifts** for that session
- Each page = one exam date × one shift × one language variant
- Page layout: three subject columns (Mathematics | Physics | Chemistry) per page
- 2021: ~78 pages per session (all dates × shifts × language variants in one PDF)
- 2022–2024: ~10–12 pages per session (fewer language variants indexed)
- Pages are text-selectable (not image-based) — suitable for direct PyMuPDF extraction without OCR

---

### CDN / Hosting Pattern by Year

| Year | PDF Host | URL Pattern | Google-Indexable? |
|------|----------|-------------|-------------------|
| 2021 | `nta.ac.in` | `nta.ac.in/Download/Notice/Notice_YYYYMMDDHHMMSS.pdf` | ✅ Yes — direct PDF link in results |
| 2022 | NIC CDN (S3WaaS) | `cdnbbsr.s3waas.gov.in/s3.../uploads/YYYY/MM/YYYYMMDDNN.pdf` | ✅ Yes — via `filetype:pdf`; not on `nta.ac.in` |
| 2023 | NIC CDN (S3WaaS) | `cdnbbsr.s3waas.gov.in/s3.../uploads/YYYY/MM/YYYYMMDDNN.pdf` | ✅ Yes — via `filetype:pdf`; not on `nta.ac.in` |
| 2024 | `nta.ac.in` | `nta.ac.in/Download/Notice/Notice_YYYYMMDDHHMMSS.pdf` | ✅ Yes — result #1 with date-specific query |
| 2025 | `nta.ac.in` | `nta.ac.in/Download/Notice/Notice_YYYYMMDDHHMMSS.pdf` | Not yet tested |

**Critical insight:** 2022 and 2023 AKs are NOT on `nta.ac.in/Download/Notice/` — they are on the NIC S3WaaS CDN with unpredictable paths. The `filetype:pdf` operator is required to surface them; plain-text queries return only coaching institute articles.

---

### Search String Results by Year

#### 2021 — Plain date+shift query works
- **Search:** `jee main 17th march 2021 shift 2 answer key from nta site`
- **Result:** Direct `nta.ac.in/Download/Notice/Notice_20210324193450.pdf` — March 2021 session, 78 pages
- **Verified:** Q ID `8643513511` confirmed on page 42 (March 17 Shift 2 English) ✅
- **Recommended format:** `jee main [date] [shift] answer key from nta site`

#### 2022 — Requires `filetype:pdf`
- **Plain query:** `jee main 28 july 2022 shift 2 answer key from nta site`
  - Result: `jeemain.nta.nic.in` wrapper page → links to NIC CDN PDF (indirect)
- **`filetype:pdf` query:** `jee main april 2023 session 2 btech answer key filetype:pdf` (session-level)
  - Result #1: `cdnbbsr.s3waas.gov.in/.../2022080776.pdf` — July 2022 Session 2, 11 pages
  - Verified: Q ID `15477154521` confirmed on page 8 ✅
- **Recommended format:** `jee main [year] session [N] btech answer key filetype:pdf`

#### 2023 — Requires `filetype:pdf`
- **Plain query:** `jee main 15 april 2023 shift 2 answer key from nta site`
  - Result: Coaching institute articles only; no NTA PDF in top 10
- **`filetype:pdf` query:** `jee main april 2023 session 2 btech answer key filetype:pdf`
  - Result #1: `cdnbbsr.s3waas.gov.in/.../2023/04/2023042948.pdf` — Session 2 Final Key, Apr 6 Shift 1, B.E/B.Tech, 12 pages ✅
  - First 3 Question IDs: `7155053682`, `7155053683`, `7155053684` (10-digit)
- **Recommended format:** `jee main [year] session [N] btech answer key filetype:pdf`

#### 2024 — Plain date+shift query works (result #1)
- **Search:** `jee main 9th april 2024 shift 1 answer key from nta site`
- **Result #1:** Direct `nta.ac.in/Download/Notice/Notice_20240424132602.pdf` — Session 2 Final AK, April 4–9 2024, 10 pages
- **Verified:** Q ID `87827056148` confirmed on page 9 (April 9 Shift 1) ✅
- **Recommended format:** `jee main [date] [shift] answer key from nta site`

---

### Recommended Search Strategy by Year

| Year | Primary search format | Fallback |
|------|-----------------------|---------|
| 2021 | `jee main [DD month YYYY] shift [N] answer key from nta site` | `jee main [year] session [N] btech answer key filetype:pdf` |
| 2022 | `jee main [year] session [N] btech answer key filetype:pdf` | Manual NTA archive browse |
| 2023 | `jee main [year] session [N] btech answer key filetype:pdf` | Manual NTA archive browse |
| 2024 | `jee main [DD month YYYY] shift [N] answer key from nta site` | `jee main [year] session [N] btech answer key filetype:pdf` |
| 2025 | `jee main [DD month YYYY] shift [N] answer key from nta site` | Not yet tested |

**Rule of thumb:** If the year is 2022 or 2023, skip date-specific queries and go straight to `filetype:pdf` with session-level terms. For 2021, 2024, and likely 2025, date-specific plain queries surface the correct NTA PDF as result #1 or #2.

---

### Coverage Assessment

Each session-level PDF covers all dates × shifts for that session. Confirmed PDFs found:

| Session | PDF found? | Pages | Verified Q ID? |
|---------|------------|-------|---------------|
| March 2021 | ✅ | 78 | ✅ Mar 17 S2 |
| Aug 2021 (Session 3, Jul 20–27) | ✅ | 7 | — |
| Aug 3, 2021 paper | ❌ No matching AK found | — | — (anomalous date) |
| Jul 2022 Session 2 | ✅ (via filetype:pdf) | 11 | ✅ Jul 28 S2 |
| Apr 2023 Session 2 | ✅ (via filetype:pdf) | 12 | ✅ Apr 6 S1 format confirmed |
| Jan 2024 Session 1 | ✅ | 10 | ✅ Jan 31 S2 |
| Apr 2024 Session 2 | ✅ | 10 | ✅ Apr 9 S1 |
| Jan 2025 Session 1 | ✅ | 20 | ✅ Jan 23 S2 |

Not yet tested: Jan 2022 Session 1, Jan 2023 Session 1, Apr 2025 Session 2.

**Estimated coverage:** Google can surface NTA AK PDFs for the majority of 2021–2024 sessions. The `filetype:pdf` operator is the key unlock for 2022–2023. Coverage is high enough (~8/11 confirmed sessions) to bootstrap Module 1b meaningfully, with the remainder recoverable via manual NTA archive browse.

---

### Verdict

✅ **Viable as a supplementary discovery approach.** Google with `filetype:pdf` can locate NTA answer key PDFs across all tested years. PDFs contain proper NTA Question IDs in text-selectable format, matching the IDs in question papers. This approach can fill gaps left by `download_answer_keys.py`'s `classify_title()` misclassification, and can also serve as a bulk bootstrap mechanism for 2021–2024.

**Not a replacement** for fixing `classify_title()` — the NTA archive crawl is authoritative and systematic. Google discovery is best used as a targeted gap-filler for sessions not in `exam_answer_keys`.

---

*Approach 8 findings from live Playwright investigation on 2026-03-20.*
