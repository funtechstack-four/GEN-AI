# Objection windows: legal basis and how we count them

The dossier shows whether an objection window is still open. This page says where
the windows come from in law and how the agent should work out the closing date.
It's a summary for building the demo, not legal advice.

## Where the windows come from

**Lost or destroyed title (Land Registration Act, No. 3 of 2012, s.33, as amended by Act No. 28 of 2016, s.13)**

- s.33(3): the Registrar can issue a duplicate title only after publishing a notice
  in the Gazette and two local newspapers, and only "upon the expiry of sixty days
  from the date of publication in the Gazette or circulation of such newspapers;
  whichever is first".
- s.33(5): reconstructing a lost land register also needs "due notice of sixty days
  in the Gazette".
- In our data, 12,921 `lost_title` notices state 60 days, e.g. 2024-10-04:12679:
  "after the expiration of sixty (60) days from the date hereof, I shall issue a
  replacement title provided that no objection has been received within that period".

**Succession (Law of Succession Act, Cap. 160, ss.67–68)**

- s.67: no grant of representation (apart from a limited grant to collect and
  preserve assets) is made until a notice of the application has been published
  "inviting objections thereto to be made known to the court within a specified
  period of not less than thirty days from the date of publication", and that
  period has expired.
- s.68(1): objections are lodged with the court within the period in the notice,
  or a longer period if the court allows.
- So the window is whatever the notice states, and never less than 30 days.

**Registration of an instrument without the original title (transfers after succession etc.)**

- These notices (e.g. 2024-06-21:7770) say the Registrar will dispense with the
  lost title and register the transfer "after the expiration of thirty (30) days
  from the date hereof, provided no valid objection has been received".
- We haven't pinned down the exact provision behind the 30 days yet, so for these
  we only rely on the period written in the notice itself.

## How the agent should count

1. **Use the period written in the notice.** The parquet already has it in
   `objection_days` (60 for most lost titles, 30 for most transfers; 14 and 90 also
   appear). Don't assume 60 for everything.
2. **Count from the date on the notice ("from the date hereof"),** which is the
   `notice_dated` field (free text like "4th October, 2024"). This can be a day or
   two before the Gazette issue date: 12436 is dated 26 Sep 2024 but gazetted 27 Sep.
3. **If `notice_dated` is missing (543 notices), can't be parsed (9), or comes
   after `issue_date` (117, almost certainly OCR), use `issue_date`,** and say the
   date is approximate.
4. **If `objection_days` is missing, don't show a closing date.** Say the notice
   didn't state a period and add it to the advocate review list.
5. `closes_on = notice date + objection_days`, and the window is open if the sale
   date is on or before `closes_on`.

Worked example (case 1b): 12679 is dated 4 Oct 2024, 60 days → closes 3 Dec 2024.
A sale on 15 Nov 2024 is inside the window.

## What to tell the user

- Under s.33(3) the 60 days can also start from the newspaper notice if that came
  out first, and we only see the Gazette. So the closing date is "based on the
  Gazette notice", and the Registrar is the one to confirm it.
- An open window means someone can still object; a closed one doesn't mean nobody
  did. Either way the buyer still needs an official search.

## Sources

- Land Registration Act, No. 3 of 2012, s.33, Kenya Law version revised to 31 Dec 2022
  (s.33 notes "[Act No. 28 of 2016, s. 13.]"; the 60-day and "whichever is first"
  wording is still there): https://new.kenyalaw.org/akn/ke/act/2012/3/eng@2022-12-31
- Law of Succession Act, Cap. 160, ss.67–68, as quoted in *In re Estate of Quintus
  Ekessa (Deceased)* [2021] KEHC 1806 (KLR):
  https://new.kenyalaw.org/akn/ke/judgment/kehc/2021/1806/eng@2021-12-01
- Notice wording and counts: `data/extracts/gazette_notices.parquet`
  (fields `objection_days`, `notice_dated`, `issue_date`). Counts are from the
  19,360-notice extract, before the probate notices in #23.
