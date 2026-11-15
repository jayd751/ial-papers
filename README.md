# IAL Papers

Download official Edexcel IAL past papers. Physics, Chemistry, Biology, Maths and more. Straight from Pearson's servers. No account needed.

## What you can download

Question papers, mark schemes, examiner reports and grade boundaries.

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

## Use it

Close server. The top right button stops the local server when you are done. Python is only running while the window is open.

Library tab. See what you downloaded. Sort and delete. Untick a paper to download it again.

Setup tab. Pick the subjects and units you take. Then downloads stay inside your setup.

Planner tab. Works out how many past papers you need and spreads them across the weeks before the exam.

- Pick subject and units, then the paper pool: new spec only, new plus legacy, or a fixed number.
- Set your current grade and target grade. Each grade of gap asks for more papers per unit.
- Set the start date, exam date, sessions per week and minutes per session.
- It builds a calendar: papers in date order alternating units, a review every two papers, and the newest paper of each unit as a timed mock at the end.
- Tick sessions off as you do them. Plan and ticks are saved in `plan.json`.
- Download .ics to put the plan in your calendar.

The maths, briefly. Grade gap of 0 asks 2 papers per unit, then 4, 6, 8, 10 for gaps of 1 to 4. Each two papers is followed by a review session, which is the spacing. Sessions are spread evenly across the whole run-up rather than bunched at the start. If the sessions do not fit the weeks left, it says so and tells you how many per week would fit.

## Where files go

papers folder. Each paper is a PDF. Sorted by subject, unit and session.

## Files

web.py - the downloader app. Run this to start.
cli.py - same tool in the terminal.
ial.py - finds papers on Pearson.
downloader.py - downloads and checks the PDFs.
dashboard.py - makes a dashboard of what you have.
