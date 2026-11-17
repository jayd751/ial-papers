# IAL Papers

Download official Edexcel IAL past papers, mark schemes, specifications and exam dates. Physics, Chemistry, Biology, Maths and more. Straight from Pearson's servers. No account needed.

It also plans your revision around the real exam timetable and keeps a score log, so you can see whether the marks are actually going up.

## What you get

- Question papers, mark schemes, examiner reports and grade boundaries.
- The specification for a subject, one PDF, in its own folder.
- Pearson's final exam timetable, per unit, with the sitting time and duration.
- A study plan built from whichever papers you pick.
- A score log drawn by the date you sat each paper.

## Download

Click the green Code button on GitHub. Then click Download ZIP. Or run this in a terminal.

```
git clone https://github.com/jayd751/ial-papers.git
```

## Run it

You need Python 3.9 or newer. Mac already has it. Windows users get it from python.org.

### Mac

Double click start-mac.command

### Windows

Double click start-windows.bat

Your browser opens. Then you click to download papers.

## The tabs

Download tab. Pick a subject, units, years, sessions and document types. Tick regional variants if you want the A and R papers as well.

Library tab. See what you downloaded. Sort, filter and delete. Untick a paper to download it again.

Setup tab. Pick the subjects and units you take, so downloads stay inside your setup. The Specifications box on the same tab grabs the official Pearson spec for a subject. It lives in `papers/<Subject>/_Specification/`, apart from the paper grid, because a spec covers a whole subject and has no unit or session.

Planner tab. Works out how many past papers you need and spreads them across the weeks before the exam.

- Pick subject and units, then the paper pool: new spec only, new plus legacy, or a fixed number.
- Set your current grade and target grade. Each grade of gap asks for more papers per unit.
- Set the start date, exam date, sessions per week and minutes per session.
- Official exam dates. Pick a series and press Find my dates. It reads Pearson's published timetable and lists every sitting for the units you ticked, with the day, morning or afternoon, and how long it runs. One click puts the first or the last paper date into the exam field. The series defaults to the next one that has not happened yet.
- It builds a calendar month by month: papers oldest first, alternating units, a review every two papers, and the newest paper of every unit kept back as a timed mock at the end.
- Tick sessions off as you do them. The plan and the ticks are saved in `plan.json`. Ticks follow the paper, so rebuilding with a new date does not wipe them.
- Download .ics to put the plan in your calendar.

The maths, briefly. Grade gap of 0 asks 2 papers per unit, then 4, 6, 8, 10 for gaps of 1 to 4. When the pool holds more papers than that, it takes them evenly across each unit's whole history rather than only the newest, so a six-paper unit plan might start in 2019 and finish with 2026. Every two papers is followed by a review session, which is the spacing. Sessions are spread across the whole run-up rather than bunched at the start, dates only ever move forward, and the last session lands on the last free day before the exam. If the plan does not fit, it trims papers rather than mocks, says how many fit, and offers a button that sets the intensity that would fit the rest.

Scores tab. Log the mark and the total for a paper you have done. It plots a line by the date you sat each one, with a dashed trailing average of your last three. Sitting a 2019 paper today shows up as today, which is the point.

Close server. The top right button stops the local server when you are done. Python only runs while the window is open.

The download tab's year sliders start at 2022. Move them back to 2009 for the whole archive. The planner does not use them, it reads Pearson's live list.

## Subjects

The picker lists the subjects this tool is set up for, one entry each. Pearson files retired variants separately, so the raw list offers Biology, Biology-A, Biology-B, Biology-(Human) and Biology-A-(Salters-Nuffield). Those are merged into Biology here, and language qualifications are hidden. Both are one edit at the top of `ial.py` in `LANGUAGE_SUBJECTS`.

## Where files go

`papers/`. Each paper is a PDF, sorted by subject, unit and session. Specifications sit in `_Specification` under their subject and never show up in the paper grid.

## Terminal

`python3 web.py` starts the app. The same thing without a browser.

```
python3 cli.py subjects
python3 cli.py units Biology
python3 cli.py download --subject Biology --unit WBI14 --years 2024-2026
python3 cli.py spec Biology --download
python3 cli.py dates WBI14 WBI15 WBI16
python3 cli.py stats
python3 cli.py dashboard --open
```

`spec` prints every specification Pearson lists for a subject, newest first, with a star on the one it would save. `dates` prints the official sittings for those units in the next exam series, or pass `--series summer-2027` to look further out.

## Files

- `web.py` the app. Run this to start.
- `cli.py` the same tool in a terminal.
- `ial.py` talks to Pearson. Papers, specifications, timetables, and the subject list.
- `downloader.py` downloads and checks the PDFs.
- `dashboard.py` builds a dashboard of what you have.

## Notes

Everything comes from Pearson's own servers and public search index. Nothing is mirrored or scraped from a third party. Timetables are the final published versions, but Pearson can still amend a sitting, so check their useful information page near the exam.
