# Site notes: how each application site behaves

Learned from live runs with Claude in Chrome. The general rule on every site: **fill, then read
every value back from the page before submitting.** A field that looks filled often isn't
registered by the page's code.

## Greenhouse (`job-boards.greenhouse.io`, `boards.greenhouse.io`)
- **Questions up front:** `boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>?questions=true`
  returns every label, type, required flag and option. Use it to build the form file.
- **Embed form:** `job-boards.greenhouse.io/embed/job_app?for=<board>&token=<id>` has the same form
  as company career pages that wrap Greenhouse.
- **Text fields:** set with the native value setter plus `input`/`change` events. Exception:
  `type=number` fields (education years) must be typed physically.
- **Dropdowns (react-select):** script-set values don't register. Scroll the input to the middle
  of the screen (`scrollIntoView({block:'center', behavior:'instant'})`), click it, type the
  option text, wait about 1 second, press Enter. Read the value back from `[class*=single-value]`.
  Fields near the top of the page can't be centred; take a screenshot for coordinates.
- **School search** often needs a prefix (e.g. "University of Texas", then pick the campus).
  See `education.school_search_hint` in your profile.
- **Discipline lists** rarely have niche majors; `education.discipline_dropdown_order` sets the fallback.
- If Submit does nothing, look for `[id$=-error]` elements, fix those fields, click again.
- Some boards send an email security code before submit. It expires in about 30 minutes: the
  applicant reads it and enters it, or approves Claude reading it from their inbox.

## Ashby (`jobs.ashbyhq.com`)
- Open `/application` directly. The form renders with JavaScript, so read it from the page.
- **The first keystrokes after a page load or a script call are often dropped.** Click the field by
  coordinates, type, read it back, retype anything empty.
- **Yes/No buttons, radios and checkboxes** can look selected without registering. Click by screen
  coordinates; if needed, click a different option first and then the right one.
- Typeahead fields (location, "How did you hear"): type, wait 1 second, press Enter or click the
  option, then verify.
- Date fields ("Pick date..."): click, type MM/DD/YYYY, press Enter.
- Submit, then read the page for "Missing entry" (fix and resubmit) or "successfully submitted".

## Lever (`jobs.lever.co`)
- Upload the resume **first** and wait: parsing overwrites name, email and phone.
- Submit usually needs **two clicks**: the first runs an invisible CAPTCHA check. Success means
  the address ends in `/thanks`. If a visible CAPTCHA appears, hand it to the applicant.
- Check only required consent boxes. Leave "contact me about future opportunities" unchecked.

## Rippling (`ats.rippling.com`)
- Resume parsing fills name, email, phone, location, LinkedIn and GitHub. Verify each.
- Dropdowns are click-to-open lists. Graduation is often a range option ("Between August 2027 -
  December 2027"). SMS consent: No.

## Workday, iCIMS, Taleo, SuccessFactors, Oracle
- Each company needs its own account, which accepts that site's terms. **The applicant creates
  the account and signs in**; Claude can continue from there.
- Workday: choose "Apply Manually". Pages: My Information, My Experience, Application Questions,
  Voluntary Disclosures, Self Identify, Review. Check for red error banners after each page.

## Google Sheets (if you mirror the tracker)
- Use the Name box (top-left cell reference) to jump to a cell, type the value, press Enter.
- **Never type a tab character inside text**: it lands inside the cell. Press the Tab key instead,
  or paste a whole block: write tab-separated text to the clipboard and paste at the first cell.
- To keep the Status dropdown on a new row, copy a Status cell from an existing row and paste it.
- Verify writes by reading the sheet back:
  `fetch('/spreadsheets/d/<id>/gviz/tq?tqx=out:csv&gid=<gid>&range=A1:J20')` from the sheet tab.

## Gmail (for the inbox sync)
- Search results render only when the tab is visible: take a screenshot before reading rows.
- Read-only: never click links in emails, reply, archive or delete.

## Learned in use
(Claude appends new quirks here after each session.)
- Workday: the first "Save and Continue" click after editing a text field often only blurs the field; click again and re-read the step indicator. Dropdown buttons work reliably with click, read `[role=option]`, then ArrowDown N + Enter, then read the button text back.
- Workday "How did you hear" prompts with nested categories: typing + Enter auto-picks the first match (e.g. "LinkedIn Connection Post"); browse the category list with the mouse wheel inside the list instead.
- Workday LinkedIn field rejects `linkedin.com/in/x/`; use `https://www.linkedin.com/in/x`.
- EA careers (Avature): the EEO step may silently advance to the screening-questions step while the title stays the same; check the step list. School and country fields are select2 typeaheads.
- Google Sheet mirror: always read the tail of the sheet right before writing. Other runs append rows too, so a remembered "next free row" can overwrite their rows.
