# Progress Log: Global Monitoring & Real Estate Intelligence System

A day by day record of what has actually been built and verified on this project, reconstructed from real dated evidence in the code, the README files, and the persisted reports, not from memory alone. Each entry describes what changed and, where it matters, what real problem it fixed. I will keep adding to this as work continues.

## 2026-09-09: first real content, no pipeline yet

The knowledge base was seeded with real, sourced material collected through live web search: Bank Al-Maghrib's rate decision and growth forecasts, 2026 tourist arrival figures, and a real account of how Moroccan real estate responded to the COVID era. A hand-assembled example daily report was also produced that day to show what the system's output format looks like when built from genuine research, since the live pipeline itself was not wired up to real credentials yet.

## 2026-09-10: the first real, automated end to end run

With real API keys in place, the system ran for the first time as an actual automated pipeline rather than a hand-assembled example. All five monitoring agents made real web searches and real model calls. The run also surfaced two genuine bugs worth recording because they shaped later fixes: some article dates came back in a format the system did not yet parse, silently dropping those events, and Gemini's free tier rate limit was hit partway through, which failed the debate stage that day. Both were logged honestly in the run's trace rather than papered over.

## 2026-09-11: history, exports, and notifications

This was a heavy build day. Each monitoring agent was pointed at a curated list of real, named news and research outlets instead of an unrestricted search, which fixed searches landing on a homepage instead of a real article. A small SQLite index was added over the run history so past reports could be browsed instead of only the most recent one. PDF export of a report was built. Daily WhatsApp and email notifications were built as optional, honestly skipped channels when credentials are missing. Following a request to also watch for international shocks that could reach Marrakech through tourism or costs, the news coverage was broadened to more global outlets and to energy and commodity sources specifically.

## 2026-09-14: explaining events, not just listing them, plus a new API key

This is the day the "why does this matter" gap was addressed directly. Judge, the stage that turns an event into a structured assessment, gained a plain language rationale field so a person can see the reasoning behind a direction and confidence call, not only the verdict numbers. Every event also got its own small notes box, so a note or question left while reading a report is saved onto that run permanently rather than lost when the page reloads. Separately, a newly supplied Gemini API key was tested and verified, then set as the active key. It was also confirmed that this project has no external database of any kind, only a local file index, and CallMeBot was wired in as a free alternative to Twilio for WhatsApp notifications, per your request.

## 2026-09-15: a real production bug, a full data audit, and the knowledge base going live

This was the largest single day of work so far, in three parts.

First, CallMeBot was diagnosed as not sending messages because two required fields were still blank in the configuration, and after you confirmed you had genuinely completed the opt in steps with no reply, we discussed alternatives (Twilio, email only, or Meta's WhatsApp Business Platform) and you chose to explore Meta, which is still pending your own Meta developer credentials since account creation is something only you can do.

Second, a real and previously undiscovered production bug was found and fixed: every single Judge assessment had been silently failing on every run since the feature existed, because a Gemini rate limit response was being treated the same as a genuinely bad API key and never retried. This was traced to the exact line of code causing it and fixed with real retry logic that waits and tries again, which is also why the explanation feature had appeared to not work at all when you first went looking for it. The same explanation was then extended to the PDF export, which had been left out the first time by an earlier, narrower scope decision.

Third, at your request, the large "Orchid data" folder already sitting in the project was fully analyzed rather than assumed from file names. That turned up genuine internal company material inside a set of scanned documents: Orchid Island's own listing for a building in the Sidi Ghanem industrial zone, two real land title records for a parcel on the Casablanca road, and dossiers for two investment opportunities that were under evaluation, plus an old 2008 feasibility study for an unrelated desert resort project kept as market precedent. The same folder also held about 120,000 real scraped Marrakech property listings across four platforms, which were cleaned and aggregated into real comparable pricing figures, with a special focus on Palmeraie luxury villas given Orchid Island's positioning. Three files were found to be fabricated data dressed up as real records and were excluded entirely, and one unrelated confidential legal document about a medical clinic sale was found in the same folder and left out as well, since it has nothing to do with real estate.

All of that real, verified content was then turned into six new knowledge base files, and Phase 4, the retrieval stage that had been sitting unbuilt since the project began, was actually built: a real keyword based search engine that the Judge stage now queries for every single event, so an assessment can be grounded in Orchid Island's own data when it genuinely applies, with the exact source shown in the Digest Console under a "Grounded in" line. Both README files were updated to describe this honestly, including its real limits, and the full test suite grew to 139 passing tests.

## 2026-09-16: making today's report actually look like today's report

Two issues were raised after using the system with fresh eyes. The first turned out to be a misunderstanding rather than a bug: the report you were looking at was a real, unedited snapshot from before the previous day's fixes, and reports never update themselves after the fact, so it still said Phase 4 was not implemented because that was true at the moment it was generated. The second was a genuine gap: the Digest Console had no way of telling you whether what you were looking at was actually today's report or an old one left over from a previous visit. That was fixed: the console now shows a clear status line saying whether today's report is ready or still needs to be run, the run picker was relabeled as "Previous reports" so older runs read as history rather than as the current one, and opening an older report now shows a visible notice saying so, with a one click way back to today's report.

## What is still open

A few things flagged along the way still need your input rather than more building: confirming whether the Tingis Plaza and Atlas Golf Marrakech opportunities, and the two Route de Casablanca land parcels, are live matters, closed ones, or just comparables being tracked; confirming whether the Sidi Ghanem prices are sale prices or rent; and, if you want mornings to start with a report already waiting rather than needing a manual click, deciding whether to set up a real automatic daily run.
